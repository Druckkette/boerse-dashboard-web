import pytest

from app.repositories.portfolio import PortfolioImportResult
from app.schemas import PortfolioImportRequest
from app.services import portfolio as portfolio_service
from app.services.portfolio import parse_positions_csv


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
