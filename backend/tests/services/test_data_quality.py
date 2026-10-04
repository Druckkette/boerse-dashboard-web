from __future__ import annotations

from datetime import date, timedelta

from app.schemas import DataQualityEvent, PortfolioPosition
from app.services import data_quality
from app.services.data_quality import assess_position_quality


def _position(**updates) -> PortfolioPosition:
    values = {
        "ticker": "NVDA",
        "name": "NVIDIA",
        "shares": 10,
        "entry_price": 100,
        "current_price": 120,
        "market_value": 1200,
        "pnl_pct": 20,
        "weight_pct": 10,
        "atr_pct": 3.2,
        "beta": 1.4,
        "beta_balancer_score": 1.3,
        "risk_contribution": 0.13,
        "status": "ok",
        "pnl_abs": 200,
        "currency": "USD",
    }
    values.update(updates)
    return PortfolioPosition(**values)


def test_position_quality_is_trusted_for_complete_current_data() -> None:
    today = date.today()
    result = assess_position_quality(
        [_position()],
        latest_by_ticker={"NVDA": today},
        fundamentals_by_ticker={"NVDA": today},
        today=today,
    )

    assert result["NVDA"]["status"] == "trusted"


def test_position_quality_is_limited_for_stale_or_incomplete_metrics() -> None:
    today = date.today()
    result = assess_position_quality(
        [_position(atr_pct=None)],
        latest_by_ticker={"NVDA": today - timedelta(days=7)},
        fundamentals_by_ticker={},
        today=today,
    )

    assert result["NVDA"]["status"] == "limited"
    assert "veraltet" in result["NVDA"]["detail"]
    assert "ATR oder Beta fehlt" in result["NVDA"]["detail"]


def test_position_quality_blocks_implausible_position_values() -> None:
    today = date.today()
    result = assess_position_quality(
        [_position(current_price=900, market_value=9000, pnl_pct=800)],
        latest_by_ticker={"NVDA": today},
        fundamentals_by_ticker={"NVDA": today},
        today=today,
    )

    assert result["NVDA"]["status"] == "blocked"
    assert "plausibilitätskritisch" in result["NVDA"]["detail"]


def test_informational_dividend_does_not_create_warning_issue() -> None:
    issues = data_quality._build_issues(
        open_tickers=["2318.HK"],
        missing_price_tickers=[],
        stale_price_tickers=[],
        missing_yahoo_tickers=[],
        missing_fundamentals=[],
        missing_risk_metrics=[],
        missing_stops=[],
        implausible=[],
        isin_mappings_count=1,
        freshness=[],
        events=[
            DataQualityEvent(
                ticker="2318.HK",
                event_type="dividend_candidate",
                event_date="2026-08-18",
                label="Mögliche Ausschüttung",
                detail="Roh- und adjustierter Kurs unterscheiden sich.",
                severity="info",
            )
        ],
    )

    assert all(issue.key != "corporate_action_candidates" for issue in issues)


def test_critical_split_candidate_creates_warning_issue() -> None:
    issues = data_quality._build_issues(
        open_tickers=["TEST"],
        missing_price_tickers=[],
        stale_price_tickers=[],
        missing_yahoo_tickers=[],
        missing_fundamentals=[],
        missing_risk_metrics=[],
        missing_stops=[],
        implausible=[],
        isin_mappings_count=1,
        freshness=[],
        events=[
            DataQualityEvent(
                ticker="TEST",
                event_type="split_candidate",
                event_date="2026-08-18",
                label="Möglicher Aktiensplit",
                detail="Extremer Rohkurs-Sprung.",
                severity="critical",
            )
        ],
    )

    issue = next(issue for issue in issues if issue.key == "corporate_action_candidates")
    assert issue.tickers == ["TEST"]


def test_etf_fundamentals_are_inapplicable_but_prices_and_risk_remain_required() -> None:
    today = date.today()
    positions = [_position(ticker="ARKK.L", name="ARK Innovation"), _position(ticker="ZPDH.DE", name="SPDR")]
    result = assess_position_quality(
        positions, latest_by_ticker={p.ticker: today for p in positions},
        fundamentals_by_ticker={"ARKK.L": today - timedelta(days=30)}, today=today,
    )
    assert all(item["status"] == "trusted" for item in result.values())
    result = assess_position_quality(
        [_position(ticker="ARKK.L", name="ARKK.L", atr_pct=None)],
        latest_by_ticker={}, fundamentals_by_ticker={}, today=today,
    )
    assert result["ARKK.L"]["status"] == "blocked"
    assert "ATR oder Beta fehlt" in result["ARKK.L"]["detail"]
    assert "Fundamental-Snapshot fehlt" not in result["ARKK.L"]["detail"]


def test_persisted_etf_classification_excludes_unknown_ticker() -> None:
    today = date.today()
    result = assess_position_quality(
        [_position(ticker="FUND", name="Example")], latest_by_ticker={"FUND": today},
        fundamentals_by_ticker={}, today=today, instrument_types={"FUND": "etf"},
    )
    assert result["FUND"]["status"] == "trusted"
    assert not data_quality._requires_fundamentals(_position(ticker="FUND"), {"FUND": "etf"})
    assert data_quality._requires_fundamentals(_position(), {})


def test_diagnostics_exclude_etf_snapshots_and_keep_reached_stop_warning(monkeypatch) -> None:
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    now = datetime.now(UTC)
    positions = [
        _position(ticker="ARKK.L", name="ARK Innovation", stop_price=125),
        _position(ticker="ZPDH.DE", name="SPDR", stop_price=100),
    ]
    db = MagicMock()
    db.scalar.return_value = 2
    db.execute.side_effect = [
        SimpleNamespace(all=lambda: [(p.ticker, now.date(), now) for p in positions]),
        SimpleNamespace(all=lambda: [("ARKK.L", now.date() - timedelta(days=30))]),
    ]
    db.scalars.return_value.all.return_value = [
        SimpleNamespace(ticker=p.ticker, name=p.name, asset_class="stock", yahoo_symbol=p.ticker, metadata_json={})
        for p in positions
    ]
    session = MagicMock()
    session.__enter__.return_value = db
    monkeypatch.setattr(data_quality, "SessionLocal", lambda: session)
    monkeypatch.setattr(data_quality, "get_portfolio_positions", lambda: positions)
    monkeypatch.setattr(data_quality, "get_freshness", lambda: SimpleNamespace(services=[]))
    monkeypatch.setattr(data_quality, "_detect_corporate_action_candidates", lambda tickers: [])

    result = data_quality.build_data_diagnostics()
    assert result.missing_fundamentals_count == 0
    assert [issue.key for issue in result.issues] == ["stops_already_reached"]
    assert result.issues[0].tickers == ["ARKK.L"]
    assert result.decision_status == "limited"
    assert result.stop_coverage_pct == 100
    assert "1 Hinweise" in result.summary
