from types import SimpleNamespace

import pytest

from app.schemas import TradeJournalImageSet
from app.services import trade_journal


def test_trade_journal_stop_distance_and_deviation() -> None:
    buy = SimpleNamespace(stop_price=90.0)

    assert trade_journal._stop_distance_pct(120.0, 100.0) == 16.67
    assert trade_journal._stop_deviation(buy, price=120.0) == 33.33


def test_trade_journal_realized_pnl_uses_eur_usd(monkeypatch) -> None:
    buy = SimpleNamespace(price=100.0, shares=10.0)
    monkeypatch.setattr(
        trade_journal,
        "get_eur_usd_rate",
        lambda: SimpleNamespace(rate=1.25),
    )

    pnl_eur, pnl_pct = trade_journal._realized_pnl(buy, price=120.0, shares=5.0)

    assert pnl_eur == 80.0
    assert pnl_pct == 20.0


def test_trade_journal_image_limit_is_enforced() -> None:
    oversized = TradeJournalImageSet(daily_chart="x" * (trade_journal.IMAGE_DATA_URL_LIMIT + 1))

    with pytest.raises(ValueError, match="daily_chart ist zu groß"):
        trade_journal._validate_images(oversized)


def test_trade_journal_stock_snapshot_includes_stock_detail_sources(monkeypatch) -> None:
    monkeypatch.setattr(
        trade_journal,
        "get_stock_assessment",
        lambda ticker: SimpleNamespace(
            model_dump=lambda mode: {
                "ticker": ticker,
                "scores": {"overall": 82},
                "metrics": {"last_close": 100},
                "checks": [{"label": "Preis", "passed": True}],
            }
        ),
    )
    monkeypatch.setattr(
        trade_journal,
        "get_stock_fundamentals",
        lambda ticker: SimpleNamespace(model_dump=lambda mode: {"ticker": ticker, "source": "database", "item": {"ticker": ticker}}),
    )
    monkeypatch.setattr(
        trade_journal,
        "get_institutional_13f_for_ticker",
        lambda ticker: SimpleNamespace(model_dump=lambda mode: {"ticker": ticker, "source": "database", "item": {"holder_count": 12}}),
    )
    monkeypatch.setattr(
        trade_journal,
        "get_relative_strength_for_ticker",
        lambda ticker: SimpleNamespace(model_dump=lambda mode: {"found": True, "item": {"rating": 91}}),
    )
    monkeypatch.setattr(
        trade_journal,
        "get_price_history",
        lambda ticker, range_key: SimpleNamespace(model_dump=lambda mode: {"ticker": ticker, "points": [{"date": "2026-06-23"}]}),
    )

    snapshot = trade_journal._stock_snapshot("NVDA")

    assert snapshot["snapshot_schema"] == "stock_detail_v2"
    assert snapshot["assessment"]["scores"]["overall"] == 82
    assert snapshot["checks"][0]["label"] == "Preis"
    assert snapshot["fundamentals"]["item"]["ticker"] == "NVDA"
    assert snapshot["institutional_13f"]["item"]["holder_count"] == 12
    assert snapshot["relative_strength"]["item"]["rating"] == 91
    assert snapshot["price_history"]["points"][0]["date"] == "2026-06-23"
