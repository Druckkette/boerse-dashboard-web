from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.portfolio.trade_republic import parse_transaction_export_csv, reconstruct_open_positions
from app.repositories.portfolio import PortfolioImportResult, TradeRepublicImportResult
from app.repositories.portfolio import PortfolioPositionRow
from app.schemas import PortfolioImportRequest, TradeRepublicTransactionImportRequest
from app.services import portfolio as portfolio_service
from app.services.portfolio import parse_positions_csv


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "portfolio"
REFERENCE_TR_EXPORT = Path(__file__).resolve().parents[5] / "boerse-dashboard-github" / "TR" / "Transaktionsexport.csv"


def test_parse_positions_csv_supports_semicolon_and_decimal_comma() -> None:
    content = """Ticker;Name;Stück;Einstandskurs;Währung;Kaufdatum
NVDA;NVIDIA;12;91,20;USD;2025-01-15
MSFT;Microsoft;6;382,10;USD;2025-02-01
"""

    result = parse_positions_csv(content)

    assert result.errors == []
    assert result.rows_total == 2
    assert result.positions[0].ticker == "NVDA"
    assert result.positions[0].shares == 12
    assert result.positions[0].entry_price == 91.2
    assert result.positions[0].currency == "USD"


def test_parse_positions_csv_reports_missing_required_columns() -> None:
    result = parse_positions_csv("Ticker;Name\nNVDA;NVIDIA\n")

    assert result.positions == []
    assert result.errors
    assert "shares" in result.errors[0]
    assert "entry_price" in result.errors[0]


def test_portfolio_import_uses_repository_on_save(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_upsert(rows, *, source: str, file_name: str, replace_open_positions: bool):
        captured["rows"] = rows
        captured["source"] = source
        captured["file_name"] = file_name
        captured["replace_open_positions"] = replace_open_positions
        return PortfolioImportResult(import_id="import-1", rows_imported=len(rows))

    monkeypatch.setattr(portfolio_service.portfolio_repository, "upsert_imported_positions", fake_upsert)

    result = portfolio_service.import_portfolio_positions(
        PortfolioImportRequest(
            file_name="website-upload.csv",
            content="Ticker,Shares,Entry_Price,Current_Price\nAAPL,3,100,130\n",
            dry_run=False,
            replace_open_positions=True,
        )
    )

    assert result.ok is True
    assert result.import_id == "import-1"
    assert result.rows_imported == 1
    assert captured["file_name"] == "website-upload.csv"
    assert captured["replace_open_positions"] is True
    assert captured["rows"][0].ticker == "AAPL"


def test_portfolio_positions_include_cached_atr(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        PortfolioPositionRow(
            ticker="AAPL",
            name="Apple",
            shares=3,
            entry_price=100,
            current_price=130,
            currency="USD",
            buy_date=date(2025, 1, 15),
            broker="Test",
            account="Main",
        )
    ]
    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_open_positions", lambda: rows)
    monkeypatch.setattr(portfolio_service.prices_repository, "list_price_bars", lambda ticker: _price_bars())

    positions = portfolio_service.get_portfolio_positions()
    snapshot = portfolio_service.get_portfolio_snapshot()

    assert positions[0].atr_pct > 0
    assert snapshot.portfolio_atr_pct == pytest.approx(positions[0].atr_pct)
    assert snapshot.kpis[-1].label == "Portfolio ATR"


def test_empty_portfolio_returns_empty_state_not_demo_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_open_positions", lambda: [])
    monkeypatch.setattr(portfolio_service.portfolio_repository, "get_cash_balance", lambda: 0.0)

    positions = portfolio_service.get_portfolio_positions()
    snapshot = portfolio_service.get_portfolio_snapshot()

    assert positions == []
    assert snapshot.positions == []
    assert snapshot.total_value == 0
    assert snapshot.kpis[1].label == "Positionen"
    assert snapshot.kpis[1].value == "0"
    assert snapshot.kpis[1].detail == "Import offen"


def test_trade_republic_parser_handles_broker_edge_cases() -> None:
    rows = parse_transaction_export_csv((FIXTURE_DIR / "trade_republic_edge_cases.csv").read_text())

    assert len(rows) == 8
    assert rows[1].transaction_type == "buy"
    assert rows[1].price == 100.5
    assert rows[1].external_id == "tr:tx-nvda-buy"
    assert rows[2].transaction_type == "dividend"
    assert rows[-2].transaction_type == "warrant_exercise"
    assert rows[-1].transaction_type == "exchange"

    positions, skipped = reconstruct_open_positions(rows, {"US67066G1040": "NVDA"})

    assert skipped == []
    assert len(positions) == 1
    assert positions[0].ticker == "NVDA"
    assert positions[0].shares == pytest.approx(15)
    assert positions[0].avg_buy_price == pytest.approx(50.25)


def test_trade_republic_import_maps_current_reference_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_isin_mappings", lambda: {})
    content = (FIXTURE_DIR / "trade_republic_reference_sample.csv").read_text()

    result = portfolio_service.import_trade_republic_transaction_export(
        TradeRepublicTransactionImportRequest(
            file_name="trade_republic_reference_sample.csv",
            content=content,
            dry_run=True,
            replace_open_positions=False,
        )
    )

    assert result.ok is True
    assert result.transactions_total == 5
    assert {position.ticker for position in result.positions} == {"APP", "VRT", "ARKK.L"}
    assert {mapping.isin: mapping.ticker for mapping in result.mappings} == {
        "US03831W1080": "APP",
        "US92537N1081": "VRT",
        "IE000GA3D489": "ARKK.L",
    }
    assert [item.asset_class for item in result.skipped_positions] == ["DERIVATIVE"]


def test_trade_republic_import_save_calls_repository_with_transactions(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_import(*, transactions, positions, mappings, file_name: str, replace_open_positions: bool):
        captured["transactions"] = transactions
        captured["positions"] = positions
        captured["mappings"] = mappings
        captured["file_name"] = file_name
        captured["replace_open_positions"] = replace_open_positions
        return TradeRepublicImportResult(
            import_id="tr-import-1",
            rows_imported=len(positions),
            transactions_imported=len(transactions),
        )

    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_isin_mappings", lambda: {})
    monkeypatch.setattr(portfolio_service.portfolio_repository, "import_trade_republic_transactions", fake_import)

    result = portfolio_service.import_trade_republic_transaction_export(
        TradeRepublicTransactionImportRequest(
            file_name="tr-export.csv",
            content=(FIXTURE_DIR / "trade_republic_reference_sample.csv").read_text(),
            dry_run=False,
            replace_open_positions=True,
        )
    )

    assert result.ok is True
    assert result.import_id == "tr-import-1"
    assert result.rows_imported == 3
    assert result.transactions_total == 5
    assert captured["file_name"] == "tr-export.csv"
    assert captured["replace_open_positions"] is True
    assert {position.ticker for position in captured["positions"]} == {"APP", "VRT", "ARKK.L"}
    assert captured["mappings"]["US03831W1080"] == "APP"


@pytest.mark.skipif(not REFERENCE_TR_EXPORT.exists(), reason="Reference Streamlit TR export is not checked out locally.")
def test_trade_republic_import_matches_github_reference_export(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_isin_mappings", lambda: {})
    content = REFERENCE_TR_EXPORT.read_text(encoding="utf-8-sig")

    result = portfolio_service.import_trade_republic_transaction_export(
        TradeRepublicTransactionImportRequest(
            file_name=REFERENCE_TR_EXPORT.name,
            content=content,
            dry_run=True,
            replace_open_positions=False,
        )
    )

    expected_open_tickers = {
        "APP",
        "ARKK.L",
        "BE",
        "2318.HK",
        "ALAB",
        "CLS",
        "GLW",
        "LRCX",
        "MRVL",
        "MU",
        "NVDA",
        "VRT",
    }
    assert result.ok is True
    assert result.rows_total > 2000
    assert expected_open_tickers.issubset({position.ticker for position in result.positions})
    assert len(result.mappings) <= 20
    assert {item.asset_class for item in result.skipped_positions} == {"DERIVATIVE"}


@pytest.mark.skipif(not REFERENCE_TR_EXPORT.exists(), reason="Reference Streamlit TR export is not checked out locally.")
def test_trade_republic_save_accepts_github_reference_export(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_import(*, transactions, positions, mappings, file_name: str, replace_open_positions: bool):
        captured["transactions"] = transactions
        captured["positions"] = positions
        captured["mappings"] = mappings
        captured["file_name"] = file_name
        captured["replace_open_positions"] = replace_open_positions
        return TradeRepublicImportResult(
            import_id="tr-reference-import",
            rows_imported=len(positions),
            transactions_imported=len(transactions),
        )

    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_isin_mappings", lambda: {})
    monkeypatch.setattr(portfolio_service.portfolio_repository, "import_trade_republic_transactions", fake_import)

    result = portfolio_service.import_trade_republic_transaction_export(
        TradeRepublicTransactionImportRequest(
            file_name=REFERENCE_TR_EXPORT.name,
            content=REFERENCE_TR_EXPORT.read_text(encoding="utf-8-sig"),
            dry_run=False,
            replace_open_positions=True,
        )
    )

    assert result.ok is True
    assert result.import_id == "tr-reference-import"
    assert result.rows_imported == 12
    assert result.transactions_total == 2317
    assert captured["file_name"] == "Transaktionsexport.csv"
    assert captured["replace_open_positions"] is True
    assert {position.ticker for position in captured["positions"]} >= {"NVDA", "APP", "VRT", "ALAB"}
    assert captured["mappings"]["US67066G1040"] == "NVDA"


def _price_bars(periods: int = 40):
    return [
        SimpleNamespace(
            date=date.fromordinal(date(2026, 1, 1).toordinal() + offset),
            open=100 + offset,
            high=102 + offset,
            low=98 + offset,
            close=100 + offset,
            adj_close=100 + offset,
            volume=1_000_000,
        )
        for offset in range(periods)
    ]
