"""Read-only, independent request path for the five informational scores."""

from datetime import date

from app.domain.market import context_scores as scores
from app.domain.market.equal_weight_breadth import compute_equal_weight_breadth_status
from app.domain.market.volatility import VOLATILITY_TICKERS, compute_volatility_dashboard
from app.repositories.market import MarketRepositoryUnavailable
from app.schemas import MarketContextScoresResponse
from app.services import market


def get_market_context_scores(*, ticker="^GSPC", as_of: date | None = None):
    ticker = market._normalize_ampel_ticker(ticker)
    logic = market._selected_market_ampel_logic()
    bars, _ = market._load_cached_index_ohlcv(ticker, start_date=date(1900, 1, 1))
    bars = market._confirmed_ampel_bars(bars)
    if as_of is not None:
        bars = [p for p in bars if p.date <= as_of]
    points = list(
        market._cached_ampel_calculation(
            tuple(market._trend_bar_from_ohlcv(p) for p in bars), ticker, logic
        )
    )
    cutoff = (
        date.fromisoformat(points[-1].date)
        if points
        else as_of or market.completed_us_market_session().date
    )
    notes = []

    # Sources are independent: a breadth/volatility failure must not hide the
    # index, Powertrend or the authoritative ampel loaded by its own endpoint.
    def load(name, fn, empty):
        try:
            return fn()
        except (MarketRepositoryUnavailable, TimeoutError, ConnectionError, ValueError, TypeError):
            notes.append(
                f"{name}: Daten nicht verfügbar; betroffene Kriterien werden nicht bewertet."
            )
            return empty

    cached_breadth = load(
        "Marktbreite",
        lambda: market.market_repository.list_breadth_daily(
            universe=market.DEFAULT_MARKET_UNIVERSE_KEY, limit=500
        ),
        [],
    )
    breadth_by_date = {r.date.isoformat(): r for r in cached_breadth if r.date <= cutoff}
    rows = []
    for p in points[-300:]:
        r = breadth_by_date.get(p.date)
        metadata = (r.metadata_json or {}) if r else {}
        row = {
            key: getattr(r, key, None)
            for key in [
                "advancers",
                "decliners",
                "ad_line",
                "mcclellan",
                "pct_above_20sma",
                "pct_above_50sma",
                "pct_above_200sma",
                "new_highs",
                "new_lows",
            ]
        }
        row.update(
            date=p.date,
            up_volume=market._metadata_float(metadata, "up_volume"),
            down_volume=market._metadata_float(metadata, "down_volume"),
        )
        coverage = market._metadata_float(metadata, "coverage_ratio")
        row["coverage_pct"] = coverage * 100 if coverage is not None else None
        if scores.finite(row["new_highs"]) and scores.finite(row["new_lows"]):
            row["nh_nl_ratio"] = row["new_highs"] / row["new_lows"] if row["new_lows"] > 0 else None
        rows.append(row)
    if points and points[-1].date not in breadth_by_date:
        notes.append(
            "Marktbreite: Für die bestätigte Indexsitzung fehlen Werte; kein Ersatz durch einen anderen Datenstand."
        )

    ad = []
    for i, p in enumerate(points):
        previous = points[max(0, i - 20) : i]
        window = [breadth_by_date.get(x.date) for x in [*previous, p]]
        valid = (
            len(previous) == 20
            and all(r and scores.finite(r.ad_line) for r in window)
            and all(x.price_data_complete and scores.finite(x.high) for x in [*previous, p])
        )
        if not valid:
            ad.append(None)
        else:
            ad.append(
                p.close >= 0.998 * max(x.high for x in previous)
                and window[-1].ad_line < max(r.ad_line for r in window[:-1])
            )
    ad_score = scores.confirmed_warning(ad, enter=3, leave=2)
    ad_divergence = ad_score == 0 if ad_score is not None else None

    ew = load(
        "Equal Weight",
        lambda: {
            ticker: [
                p
                for p in market._confirmed_ampel_bars(
                    market.market_repository.load_cached_ohlcv(ticker, start_date=date(1900, 1, 1))
                )
                if p.date <= cutoff
            ]
            for ticker in market.EQUAL_WEIGHT_MARKET_TICKERS
        },
        {},
    )
    ew_summary = {}
    # Full252-session high plus current same-date prices are required. Cached
    # fallback 'wachsam' is never misrepresented as a measured neutral score.
    if ew and all(
        len(ew.get(t, [])) >= 252 and ew[t][-1].date == cutoff
        for t in market.EQUAL_WEIGHT_MARKET_TICKERS
    ):
        ew_summary = compute_equal_weight_breadth_status(
            ew, session_dates=[date.fromisoformat(p.date) for p in points]
        ).to_dict()
        if ew_summary["source"] != "database":
            notes.append("Equal Weight: Vollständiges252-Sitzungs-Fenster noch nicht drei Sitzungen bestätigt.")
    else:
        notes.append(
            "Equal Weight: Gleichzeitige RSP/QQEW-Werte oder volle252-Sitzungs-Historie fehlen; keine Bewertung."
        )

    vol_series = load(
        "Volatilität",
        lambda: market.market_repository.load_cached_prices(
            VOLATILITY_TICKERS, start_date=date(1900, 1, 1)
        ),
        {},
    )
    vol_series = {
        t: [p for p in rows if p.date <= cutoff and scores.finite(p.close) and p.close > 0]
        for t, rows in vol_series.items()
    }
    vol_points = compute_volatility_dashboard(vol_series, limit=500)
    vp = vol_points[-1] if vol_points and vol_points[-1].date == cutoff.isoformat() else None
    def current(t, size):
        sessions = {p.date for p in points[-size:]}
        observed = {
            p.date.isoformat()
            for p in vol_series.get(t, [])
            if scores.finite(p.close) and p.close > 0
        }
        return len(sessions) == size and sessions.issubset(observed)

    # EMA21 compared with its value five sessions ago needs26 observations.
    # The combined regime also depends on a complete six-point SPY return.
    vix_valid, vxx_valid = current("^VIX", 21), current("VXX", 26)
    benchmark_valid = current("SPY", 6)
    if not (vp and vix_valid and vxx_valid and benchmark_valid):
        notes.append(
            "Volatilität: Fehlende Sitzung/Historie wird nicht als ruhiges Regime bewertet."
        )
    if not points:
        notes.append(
            "Index: Keine bestätigten Indexdaten. ETF-Preise oder ETF-Volumen werden nicht ersatzweise verwendet."
        )
    return MarketContextScoresResponse(
        version=scores.CONTEXT_SCORE_VERSION,
        ticker=ticker,
        as_of=cutoff.isoformat(),
        phase=points[-1].phase if points else "neutral",
        scores=[
            scores.index_score(points),
            scores.breadth_score(points, rows, ad_divergence=ad_divergence),
            scores.powertrend_score(points, enabled=logic == "ibd"),
            scores.equal_weight_score(ew_summary),
            scores.volatility_score(
                vp, vix_valid=vix_valid, vxx_valid=vxx_valid, benchmark_valid=benchmark_valid
            ),
        ],
        notes=notes,
    )
