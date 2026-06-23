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
