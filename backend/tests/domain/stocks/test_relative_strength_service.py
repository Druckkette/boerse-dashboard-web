from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.stocks.relative_strength import ClosePoint
from app.repositories.relative_strength import RsRatingRow, RsRatingWrite
from app.services import relative_strength as service


def test_refresh_relative_strength_uses_cached_prices_and_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    stored: list[RsRatingWrite] = []

    def fake_load_cached_prices(tickers: list[str], *, start_date: date):
        assert "SPY" in tickers
        assert start_date < date.today()
        return {
            "SPY": _series(0.0010),
            "NVDA": _series(0.0022),
            "MSFT": _series(0.0012),
            "PLTR": _series(0.0003),
        }

    def fake_upsert(rows: list[RsRatingWrite]) -> int:
        stored.extend(rows)
        return len(rows)

    def fake_latest(*, limit: int = 100, source: str | None = None):
        return [
            RsRatingRow(
                ticker=row.ticker,
                name=row.ticker,
                date=row.date,
                rating=row.rating,
                score=row.score,
                percentile=row.percentile,
                method=row.method,
                source=row.source,
                universe_size=row.universe_size,
                metadata_json=row.metadata_json,
            )
            for row in sorted(stored, key=lambda item: item.rating, reverse=True)[:limit]
        ]

    monkeypatch.setattr(service.market_repository, "load_cached_prices", fake_load_cached_prices)
    monkeypatch.setattr(service.rs_repository, "upsert_rs_ratings", fake_upsert)
    monkeypatch.setattr(service.rs_repository, "list_latest_rs_ratings", fake_latest)

    result = service.refresh_relative_strength_ratings(tickers=["NVDA", "MSFT", "PLTR"], benchmark_ticker="SPY")

    assert result["ok"] is True
    assert result["records_written"] == 3
    assert result["top"][0]["ticker"] == "NVDA"
    assert stored[0].source == "computed"
    assert len({row.date for row in stored}) == 1
    assert all(row.metadata_json["snapshot_date"] == result["as_of"] for row in stored)
    assert all(row.metadata_json["data_as_of"] for row in stored)
    assert stored[0].metadata_json["rs_ema21_last"] is not None
    assert stored[0].metadata_json["rs_sma50_last"] is not None


def test_external_rs_refresh_uses_provider_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_external(*, tickers=None, url=service.DEFAULT_RS_CSV_URL):
        captured["tickers"] = tickers
        return {"ok": True, "source": "csv_latest", "ratings_count": 5910}

    monkeypatch.setattr(service, "refresh_external_relative_strength_ratings", fake_external)
    monkeypatch.setattr(
        service,
        "refresh_relative_strength_ratings",
        lambda **kwargs: {"ok": True, "as_of": "2026-07-30", "ratings_count": 3, "records_written": 3},
    )

    result = service.refresh_selected_relative_strength_ratings(
        tickers=["NVDA", "MSFT"],
        source="csv_latest",
    )

    assert result["ratings_count"] == 5910
    assert result["technical_lines"]["ratings_count"] == 3
    assert captured["tickers"] is None


def test_targeted_rs_line_refresh_enriches_selected_rating_without_changing_rank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: list[RsRatingWrite] = []
    selected = RsRatingRow(
        ticker="TWLO",
        name="Twilio",
        date=date(2026, 9, 2),
        rating=84,
        score=84.0,
        percentile=84.0,
        method="external_csv",
        source="csv_latest",
        universe_size=5910,
        metadata_json={"external_source": "test"},
    )
    monkeypatch.setattr(service, "configured_rs_source", lambda: "csv_latest")
    monkeypatch.setattr(
        service.market_repository,
        "load_cached_prices",
        lambda tickers, start_date: {"TWLO": _series(0.0020), "SPY": _series(0.0010)},
    )
    monkeypatch.setattr(
        service.rs_repository,
        "get_latest_rs_rating",
        lambda ticker, source=None: selected,
    )
    monkeypatch.setattr(
        service.rs_repository,
        "upsert_rs_ratings",
        lambda rows: stored.extend(rows) or len(rows),
    )

    result = service.refresh_relative_strength_line_for_ticker("TWLO")

    assert result["ok"] is True
    assert result["above_21"] is True
    assert stored[0].rating == 84
    assert stored[0].source == "csv_latest"
    assert stored[0].metadata_json["rs_ema21_last"] is not None
    assert stored[0].metadata_json["rs_line_data_as_of"] == result["as_of"]


def test_external_rs_ranking_accepts_configured_csv_source(monkeypatch: pytest.MonkeyPatch) -> None:
    row = RsRatingRow(
        ticker="NVDA",
        name="NVIDIA",
        date=date(2026, 7, 30),
        rating=99,
        score=98.2,
        percentile=99.0,
        method="external_csv",
        source="csv_latest",
        universe_size=5910,
        metadata_json={},
    )
    monkeypatch.setattr(service, "configured_rs_source", lambda: "csv_latest")
    monkeypatch.setattr(service.rs_repository, "count_latest_rs_ratings", lambda source: 5910)
    monkeypatch.setattr(
        service.rs_repository,
        "list_latest_rs_ratings",
        lambda limit, source: [row],
    )

    result = service.get_relative_strength_ranking(limit=120)

    assert result.source == "csv_latest"
    assert result.total_count == 5910
    assert result.rows[0].ticker == "NVDA"


def _series(daily_growth: float, *, days: int = 320) -> list[ClosePoint]:
    start = date(2025, 1, 1)
    price = 100.0
    points: list[ClosePoint] = []
    for offset in range(days):
        price *= 1 + daily_growth
        points.append(ClosePoint(date=start + timedelta(days=offset), close=price))
    return points
