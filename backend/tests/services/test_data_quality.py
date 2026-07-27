from datetime import date, timedelta

from app.schemas import PortfolioPosition
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
