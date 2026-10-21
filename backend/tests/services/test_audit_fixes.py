from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.repositories.portfolio import PortfolioPositionRow, PortfolioRepositoryUnavailable
from app.repositories.settings import SettingsRepositoryUnavailable
from app.schemas import PortfolioPositionWriteRequest, PortfolioSellRequest, RuntimeConfigPatch
from app.services import portfolio, settings
from app.services.money import Conversion


@pytest.mark.parametrize("quote,target,rate,close,expected", [
    ("USD", "EUR", 1 / 1.1, 110, 100),
    ("EUR", "USD", 1.1, 100, 110),
    ("USD", "USD", 1, 110, 110),
    ("GBp", "GBP", .01, 1000, 10),
])
def test_manual_positions_use_explicit_quote_units(monkeypatch, quote, target, rate, close, expected):
    calls = []
    def convert(source, dest):
        calls.append((source, dest))
        return Conversion(rate if source != dest else 1, date.today())
    monkeypatch.setattr(portfolio, "conversion", convert)
    row = PortfolioPositionRow("TEST", "Test", 10, expected, close, target, date.today(),
                               current_price_source="price_cache", current_price_currency=quote)
    normalized = portfolio._normalize_position_quote(row)
    assert normalized.current_price == pytest.approx(expected)
    assert normalized.entry_price == expected
    assert normalized.current_price_currency == target
    assert calls[0] == (quote, target)
    assert portfolio._normalize_position_quote(normalized).current_price == pytest.approx(expected)


def test_manual_valuation_is_unavailable_without_fx(monkeypatch):
    monkeypatch.setattr(portfolio, "conversion", lambda *a: None)
    row = PortfolioPositionRow("TEST", "Test", 10, 100, 110, "EUR", date.today(), current_price_source="price_cache", current_price_currency="USD")
    with pytest.raises(PortfolioRepositoryUnavailable, match="USD/EUR"):
        portfolio._normalize_position_quote(row)


def test_imported_quote_is_converted_to_listing_units_before_writing(monkeypatch):
    monkeypatch.setattr(portfolio, "conversion", lambda source, target: Conversion(1.1, date.today()))
    assert portfolio._canonical_import_quote("AAPL", 100, "EUR") == (pytest.approx(110), "USD")


def test_duplicate_csv_preview_and_write_have_one_last_row():
    result = portfolio.parse_positions_csv("ticker,shares,entry_price\nTEST,5,100\nTEST,7,105\n")
    assert not result.errors
    assert result.rows_total == 2
    assert len(result.positions) == 1
    assert result.positions[0].shares == 7 and result.positions[0].entry_price == 105
    assert "letzte Zeile" in result.warnings[0]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("field", ["fees", "tax", "price", "shares"])
def test_nonfinite_sale_input_never_reaches_storage(value, field):
    with pytest.raises(ValidationError):
        PortfolioSellRequest.model_validate({"shares": 1, "price": 10, field: value})


def test_nonfinite_csv_is_a_validation_error():
    assert portfolio.parse_positions_csv("ticker,shares,entry_price\nTEST,NaN,100\n").errors


def test_absolute_stop_mode_needs_a_price():
    with pytest.raises(ValidationError):
        PortfolioPositionWriteRequest(ticker="TEST", shares=1, entry_price=100, stop_mode="price")


def test_legacy_explicit_percent_edit_selects_percent_mode():
    request = PortfolioPositionWriteRequest(ticker="TEST", shares=1, entry_price=100, stop_pct=15)
    assert request.stop_mode == "pct"


def test_setup_database_failure_is_not_a_success(monkeypatch):
    def failed(*a):
        raise SettingsRepositoryUnavailable("synthetic outage")
    monkeypatch.setattr(settings.settings_repository, "patch_runtime_config", failed)
    response = TestClient(create_app()).patch("/api/v1/settings/runtime-config", json={"values": {"SEC_USER_AGENT": "audit test@example.com"}})
    assert response.status_code == 503
    assert "Entwurf" in response.json()["detail"]


def test_setup_file_failure_reports_committed_but_pending(monkeypatch):
    saved = []
    monkeypatch.setattr(settings.settings_repository, "patch_runtime_config", lambda values, keys: saved.append(values) or values)
    monkeypatch.setenv("APP_RUNTIME_ENV_FILE", "/dev/null/impossible/runtime.env")
    response = TestClient(create_app()).patch("/api/v1/settings/runtime-config", json={"values": {"APP_AUTH_ENABLED": "1"}})
    assert response.status_code == 503 and saved
    assert "Datenbank gespeichert" in response.json()["detail"]


def test_setup_success_writes_private_atomic_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings.settings_repository, "patch_runtime_config", lambda values, keys: values)
    target = tmp_path / "runtime.env"
    monkeypatch.setenv("APP_RUNTIME_ENV_FILE", str(target))
    result = settings.update_runtime_config(RuntimeConfigPatch(values={"SEC_USER_AGENT": "audit test@example.com"}))
    assert next(item for item in result.items if item.key == "SEC_USER_AGENT").configured
    assert "test@example.com" in target.read_text()
    assert target.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [target]
