from datetime import date
from types import SimpleNamespace
from app.services import market
from app.services.market_context_scores import get_market_context_scores
from app.repositories.market import MarketOhlcvPoint, MarketPricePoint
from tests.domain.market.test_context_scores import points


def test_index_loader_never_requests_etf_price_or_volume(monkeypatch):
    calls = []
    rows = [MarketOhlcvPoint("^GSPC", date(2024, 1, 1), 100, 101, 99, 100, 0)]

    def load(ticker, **kwargs):
        calls.append(ticker)
        assert ticker == "^GSPC"
        return rows

    monkeypatch.setattr(market.market_repository, "load_cached_ohlcv", load)
    assert market._load_cached_index_ohlcv("^GSPC", start_date=date(1900, 1, 1)) == (rows, "^GSPC")
    assert calls == ["^GSPC"]


def source_fixture(monkeypatch):
    hist = points(320)
    bydate = {p.date: p for p in hist}
    bars = [
        MarketOhlcvPoint(
            "^GSPC", date.fromisoformat(p.date), p.open, p.high, p.low, p.close, p.volume
        )
        for p in hist
    ]
    monkeypatch.setattr(market, "_selected_market_ampel_logic", lambda: "ibd")
    monkeypatch.setattr(
        market,
        "_cached_ampel_calculation",
        lambda rows, *a: tuple(bydate[str(p.date)] for p in rows),
    )
    monkeypatch.setattr(market.market_repository, "load_cached_ohlcv", lambda ticker, **kw: bars)
    breadth = [
        SimpleNamespace(
            date=b.date,
            advancers=550,
            decliners=500,
            ad_line=-500 + i,
            mcclellan=25,
            pct_above_20sma=60,
            pct_above_50sma=65,
            pct_above_200sma=55,
            new_highs=20,
            new_lows=10,
            metadata_json={"coverage_ratio": 0.95, "up_volume": 10000, "down_volume": 8000},
        )
        for i, b in enumerate(bars)
    ]
    monkeypatch.setattr(market.market_repository, "list_breadth_daily", lambda **kw: breadth)
    series = {
        t: [MarketPricePoint(t, b.date, 12 if t == "^VIX" else 100) for b in bars]
        for t in ["SPY", "^VIX", "VXX"]
    }
    monkeypatch.setattr(market.market_repository, "load_cached_prices", lambda *a, **kw: series)
    return hist, bars, breadth, series


def test_date_filtering_preserves_scores_when_future_observations_change(monkeypatch):
    hist, bars, breadth, series = source_fixture(monkeypatch)
    cutoff = bars[299].date
    a = get_market_context_scores(ticker="^GSPC", as_of=cutoff)
    for row in breadth[300:]:
        row.ad_line = 1_000_000
        row.pct_above_50sma = 0
    for t, rows in series.items():
        rows[300:] = [MarketPricePoint(t, p.date, 10000) for p in rows[300:]]
    b = get_market_context_scores(ticker="^GSPC", as_of=cutoff)
    assert a.model_dump() == b.model_dump()
    assert a.as_of == cutoff.isoformat()
    assert a.informational_only is True
    assert [s.key for s in a.scores] == [
        "index",
        "breadth",
        "powertrend",
        "equal_weight",
        "volatility",
    ]


def test_optional_universe_failure_does_not_hide_other_scores(monkeypatch):
    hist, bars, _, _ = source_fixture(monkeypatch)

    def fail(**kw):
        raise TimeoutError("unavailable")

    monkeypatch.setattr(market.market_repository, "list_breadth_daily", fail)
    result = get_market_context_scores(as_of=bars[-1].date)
    assert result.scores[0].score is not None
    assert result.scores[1].score is None
    assert result.scores[2].score is not None
    assert result.scores[3].score is not None
    assert result.notes


def test_sources_from_different_session_are_not_silently_forward_filled(monkeypatch):
    hist, bars, _, series = source_fixture(monkeypatch)
    series["^VIX"] = series["^VIX"][:-1]
    result = get_market_context_scores(as_of=bars[-1].date)
    vix = next(s for s in result.scores[-1].subscores if s.key == "vix")
    assert vix.score is None
    assert vix.data_status == "missing"
    assert result.scores[-1].score is None  # only40% VXX is available
    assert any("Volatilität" in n for n in result.notes)


def test_equal_weight_requires_three_full_252_session_windows(monkeypatch):
    _, bars, _, _ = source_fixture(monkeypatch)
    for index in [250, 251, 252]:
        result = get_market_context_scores(as_of=bars[index].date)
        assert result.scores[3].score is None
    result = get_market_context_scores(as_of=bars[253].date)
    assert result.scores[3].score is not None


def test_equal_weight_gap_cannot_be_counted_as_a_confirmation_session(monkeypatch):
    _, bars, _, _ = source_fixture(monkeypatch)
    monkeypatch.setattr(market.market_repository, 'load_cached_ohlcv',
                        lambda ticker, **kw: bars[:-2] + bars[-1:] if ticker == 'RSP' else bars)
    result = get_market_context_scores(as_of=bars[-1].date)
    assert result.scores[3].score is None


def test_vxx_requires_ema21_plus_five_previous_sessions(monkeypatch):
    _, bars, _, series = source_fixture(monkeypatch)
    series['VXX'] = series['VXX'][-25:]
    result = get_market_context_scores(as_of=bars[-1].date)
    assert result.scores[-1].subscores[1].score is None
    assert result.scores[-1].score is None


def test_missing_spy_session_does_not_supply_a_five_day_regime_return(monkeypatch):
    _, bars, _, series = source_fixture(monkeypatch)
    series['SPY'] = series['SPY'][:-3] + series['SPY'][-2:]
    result = get_market_context_scores(as_of=bars[-1].date)
    assert result.scores[-1].subscores[-1].score is None
    assert result.scores[-1].coverage_pct == 80


def test_equal_weight_does_not_reuse_a_confirmed_mode_across_an_unknown_window():
    from datetime import timedelta
    from app.domain.market.equal_weight_breadth import compute_equal_weight_breadth_status
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(9)]
    bars = [MarketOhlcvPoint('RSP', d, 99, 101, 98, 100, 1000) for d in days]
    series = {t: bars[:5] + bars[6:] for t in ['RSP', 'QQEW']}
    result = compute_equal_weight_breadth_status(
        series, lookback_trading_days=3, confirmation_days=3, session_dates=days,
    )
    assert result.source == 'insufficient'
    assert result.candidate_streak == 1
