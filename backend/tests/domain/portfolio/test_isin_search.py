from datetime import date
from types import SimpleNamespace

import pytest

from app.data_sources import isin_search
from app.domain.portfolio.trade_republic import parse_transaction_export_csv
from app.repositories.portfolio import TradeRepublicImportResult
from app.schemas import TradeRepublicTransactionImportRequest
from app.services import portfolio, tr_import_mapping
from app.services.fx import FxRate

ISIN = "US22160K1051"
CSV = f"date,type,asset_class,name,symbol,shares,price,currency,amount,fee,tax\n2026-01-02,BUY,STOCK,Costco,{ISIN},2,100,USD,-200,0,0\n"


def lookup(monkeypatch, quotes):
    monkeypatch.setattr(isin_search, "_search", lambda *args: tuple(quotes))
    return isin_search.search_isin(ISIN, "STOCK")


def test_exact_isin_single_security_is_automatic(monkeypatch):
    result = lookup(monkeypatch, [{"symbol": "COST", "quoteType": "EQUITY", "shortname": "Costco", "exchDisp": "NASDAQ"}])
    assert result["ticker"] == "COST"
    assert result["candidates"][0]["exchange"] == "NASDAQ"


def test_ambiguous_listings_require_selection(monkeypatch):
    result = lookup(monkeypatch, [{"symbol": ticker, "quoteType": "EQUITY"} for ticker in ["COST", "COST", "CTO.DE"]])
    assert result["ticker"] == ""
    assert [row["ticker"] for row in result["candidates"]] == ["COST", "CTO.DE"]


def test_wrong_identity_type_and_derivatives_are_never_mapped(monkeypatch):
    assert lookup(monkeypatch, [{"symbol": "WRONG", "quoteType": "EQUITY", "isin": "US0378331005"}])["ticker"] == ""
    assert lookup(monkeypatch, [{"symbol": "FUTURE", "quoteType": "FUTURE"}])["ticker"] == ""
    def forbidden(*args):
        pytest.fail("Derivative or invalid ISIN queried online")
    monkeypatch.setattr(isin_search, "_search", forbidden)
    assert isin_search.search_isin("DE000HM1C7B4", "DERIVATIVE")["ticker"] == ""
    assert isin_search.search_isin("US22160K1052", "STOCK")["ticker"] == ""


def test_fund_search_does_not_choose_an_underlying_share(monkeypatch):
    monkeypatch.setattr(isin_search, "_search", lambda *args: ({"symbol": "STOCK", "quoteType": "EQUITY"}, {"symbol": "FUND.DE", "quoteType": "ETF"}))
    assert isin_search.search_isin("IE00B4L5Y983", "FUND")["ticker"] == "FUND.DE"


def test_outage_is_actionable_and_retryable(monkeypatch):
    def unavailable(*args):
        raise TimeoutError()
    monkeypatch.setattr(isin_search, "_search", unavailable)
    assert "erreichbar" in isin_search.search_isin(ISIN, "STOCK")["message"]
    assert lookup(monkeypatch, [{"symbol": "COST", "quoteType": "EQUITY"}])["ticker"] == "COST"


def test_provider_search_is_exact_and_cached(monkeypatch):
    import yfinance
    calls = []
    def search(query, **kwargs):
        calls.append((query, kwargs))
        return SimpleNamespace(quotes=[{"symbol": "COST", "quoteType": "EQUITY"}])
    monkeypatch.setattr(yfinance, "Search", search)
    isin_search._search.cache_clear()
    try:
        for _ in range(2):
            assert isin_search.search_isin(ISIN, "STOCK")["ticker"] == "COST"
        assert len(calls) == 1
        assert calls[0][0] == ISIN
        assert calls[0][1]["enable_fuzzy_query"] is False
        assert calls[0][1]["timeout"] == 5
    finally:
        isin_search._search.cache_clear()


def test_existing_mappings_take_precedence_and_are_not_searched(monkeypatch):
    from app.domain.portfolio.trade_republic import resolve_isin_mappings
    rows = parse_transaction_export_csv(CSV + CSV.splitlines()[1] + "\n")
    diagnostics = resolve_isin_mappings(rows, saved_mappings={ISIN: "SAVED"}, overrides={ISIN: "MANUAL"})
    monkeypatch.setattr(tr_import_mapping, "search_isin", lambda *args: pytest.fail("Known ISIN searched"))
    assert tr_import_mapping.complete_mappings(diagnostics) == diagnostics
    assert len(diagnostics) == 1 and diagnostics[0]["ticker"] == "MANUAL"


@pytest.mark.parametrize("dry_run", [True, False])
def test_automatic_mapping_flows_to_preview_and_atomic_save(monkeypatch, dry_run):
    from app.repositories import tr_import
    captured = []
    monkeypatch.setattr(tr_import, "merged_rows", lambda rows: rows)
    monkeypatch.setattr(portfolio.portfolio_repository, "list_isin_mappings", lambda: {})
    monkeypatch.setattr(portfolio, "get_eur_usd_rate", lambda: FxRate(pair="EUR/USD", rate=1, as_of=date(2026, 1, 1), source="test"))
    monkeypatch.setattr(tr_import_mapping, "search_isin", lambda *args: {"ticker": "COST", "candidates": [], "message": "Automatic"})
    def save(**kwargs):
        captured.append(kwargs)
        return TradeRepublicImportResult(import_id="test", rows_imported=1, transactions_imported=1)
    monkeypatch.setattr(portfolio.portfolio_repository, "import_trade_republic_transactions", save)
    result = portfolio.import_trade_republic_transaction_export(TradeRepublicTransactionImportRequest(content=CSV, dry_run=dry_run))
    assert result.ok and result.positions[0].ticker == "COST"
    assert result.mappings[0].source == "automatic"
    if dry_run:
        assert captured == []
    else:
        assert captured[0]["mappings"] == {ISIN: "COST"}


def test_partial_export_keeps_saved_holdings_from_merged_history(monkeypatch):
    from app.repositories import tr_import
    monkeypatch.setattr(tr_import, "merged_rows", lambda incoming: parse_transaction_export_csv(CSV) + incoming)
    monkeypatch.setattr(portfolio.portfolio_repository, "list_isin_mappings", lambda: {ISIN: "COST"})
    monkeypatch.setattr(portfolio, "get_eur_usd_rate", lambda: FxRate(pair="EUR/USD", rate=1, as_of=date(2026, 1, 1), source="test"))
    monkeypatch.setattr(tr_import_mapping, "search_isin", lambda *args: pytest.fail("Known merged history searched"))
    dividend = CSV.splitlines()[0] + "\n2026-10-01,DIVIDEND,STOCK,Apple,US0378331005,0,0,USD,5,0,0\n"
    result = portfolio.import_trade_republic_transaction_export(TradeRepublicTransactionImportRequest(content=dividend, dry_run=True))
    assert result.ok and [row.ticker for row in result.positions] == ["COST"]


def test_incomplete_provider_payload_does_not_break_import(monkeypatch):
    assert lookup(monkeypatch, [None, {}, {"symbol": "BAD SYMBOL", "quoteType": "EQUITY"}])["ticker"] == ""


def test_lookup_budget_leaves_actionable_unresolved_result(monkeypatch):
    monkeypatch.setattr(tr_import_mapping, "search_isin", lambda *args: {"ticker": "COST", "candidates": [], "message": "Found"})
    monkeypatch.setattr(tr_import_mapping, "wait", lambda futures, timeout: (set(), set(futures)))
    result = tr_import_mapping.complete_mappings([{"isin": ISIN, "ticker": "", "asset_class": "STOCK", "source": "missing"}])
    assert result[0]["ticker"] == ""
    assert "Suchzeit" in result[0]["message"]
