from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.repositories import market as market_repository
from app.repositories.market import MarketSnapshotWrite


def test_upsert_market_snapshot_refreshes_generated_at(monkeypatch) -> None:
    original_generated_at = datetime(2026, 6, 23, 14, 35, tzinfo=UTC)
    refreshed_generated_at = datetime(2026, 6, 23, 20, 30, tzinfo=UTC)
    row = SimpleNamespace(
        ampel_phase="gelb",
        warning_count=4,
        breadth_mode="wachsam",
        volatility_regime="Neutral",
        metrics_json={},
        generated_at=original_generated_at,
    )

    class FakeScalarResult:
        def first(self):
            return row

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def scalars(self, statement):
            return FakeScalarResult()

        def commit(self):
            self.committed = True

    class FakeDateTime:
        @classmethod
        def now(cls, tz=None):
            return refreshed_generated_at

    monkeypatch.setattr(market_repository, "SessionLocal", FakeSession)
    monkeypatch.setattr(market_repository, "datetime", FakeDateTime)

    market_repository.upsert_market_snapshot(
        MarketSnapshotWrite(
            date=date(2026, 6, 23),
            ampel_phase="aufwaertstrend",
            warning_count=2,
            breadth_mode="rueckenwind",
            volatility_regime="Entspannt",
            metrics_json={"action": "test"},
        )
    )

    assert row.generated_at == refreshed_generated_at
    assert row.ampel_phase == "aufwaertstrend"
    assert row.warning_count == 2
    assert row.metrics_json == {"action": "test"}
