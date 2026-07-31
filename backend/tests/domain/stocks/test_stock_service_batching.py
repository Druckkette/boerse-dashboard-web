from datetime import date, timedelta
from types import SimpleNamespace

from app.domain.stocks.assessment import StockAssessmentBar
from app.repositories.relative_strength import RsRatingRow
from app.services import stocks as service


def test_assessment_ranking_loads_related_data_in_batches(monkeypatch) -> None:
    rs_row = RsRatingRow(
        ticker="NVDA",
        name="NVIDIA",
        date=date(2026, 7, 30),
        rating=99,
        score=98.0,
        percentile=99.0,
        method="external_csv",
        source="csv_latest",
        universe_size=5910,
        metadata_json={},
    )
    bars = _bars()
    calls = {"prices": 0, "fundamentals": 0, "institutional": 0, "computed_rs": 0}

    monkeypatch.setattr(service, "configured_rs_source", lambda: "csv_latest")
    monkeypatch.setattr(service.rs_repository, "count_latest_rs_ratings", lambda source: 5910)
    monkeypatch.setattr(
        service.rs_repository,
        "list_latest_rs_ratings",
        lambda limit, source: [rs_row],
    )

    def load_prices(tickers, *, start_date):
        calls["prices"] += 1
        assert tickers == ["NVDA"]
        return {"NVDA": bars}

    def load_fundamentals(tickers):
        calls["fundamentals"] += 1
        return {}

    def load_institutional(tickers):
        calls["institutional"] += 1
        return {}

    def load_computed_rs(tickers, *, source):
        calls["computed_rs"] += 1
        assert source == "computed"
        return {}

    monkeypatch.setattr(service.market_repository, "load_cached_ohlcv_for_tickers", load_prices)
    monkeypatch.setattr(
        service.fundamentals_repository,
        "get_latest_fundamentals_for_tickers",
        load_fundamentals,
    )
    monkeypatch.setattr(
        service.sec13f_repository,
        "get_latest_trends_for_tickers",
        load_institutional,
    )
    monkeypatch.setattr(
        service.rs_repository,
        "get_latest_rs_ratings_for_tickers",
        load_computed_rs,
    )
    monkeypatch.setattr(
        service.price_repository,
        "list_price_bars",
        lambda ticker: (_ for _ in ()).throw(AssertionError("tickerweise Kursabfrage")),
    )
    stored = []
    monkeypatch.setattr(
        service.stock_assessment_repository,
        "replace_snapshots",
        lambda rows, source_job_id="": stored.extend(rows) or len(rows),
    )

    result = service.refresh_stock_assessment_snapshots(limit=60)

    assert result["records_written"] == 1
    assert stored[0].ticker == "NVDA"
    assert calls == {"prices": 1, "fundamentals": 1, "institutional": 1, "computed_rs": 1}

    monkeypatch.setattr(
        service.stock_assessment_repository,
        "list_snapshots",
        lambda limit: [SimpleNamespace(as_of=stored[0].as_of, item_json=stored[0].item_json)],
    )
    monkeypatch.setattr(service.stock_assessment_repository, "count_snapshots", lambda: 1)

    cached = service.get_stock_assessment_ranking(limit=60)

    assert cached.source == "database"
    assert cached.rows[0].ticker == "NVDA"


def _bars() -> list[StockAssessmentBar]:
    start = date(2025, 1, 1)
    price = 100.0
    rows: list[StockAssessmentBar] = []
    for offset in range(320):
        price *= 1.001
        rows.append(
            StockAssessmentBar(
                date=start + timedelta(days=offset),
                open=price * 0.995,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=2_000_000,
            )
        )
    return rows
