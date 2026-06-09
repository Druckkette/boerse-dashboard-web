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
