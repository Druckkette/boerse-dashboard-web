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
