from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.portfolio.trade_republic import parse_transaction_export_csv, reconstruct_open_positions
from app.data_sources.yfinance_client import FetchedAfterHoursQuote
from app.repositories.market import MarketOhlcvPoint
from app.repositories.portfolio import PortfolioImportResult, TradeRepublicImportResult
from app.repositories.portfolio import PortfolioPositionRow
from app.schemas import PortfolioImportRequest, TradeRepublicTransactionImportRequest
from app.services import portfolio as portfolio_service
from app.services.fx import FxRate
from app.services.portfolio import parse_positions_csv


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "portfolio"
REFERENCE_TR_EXPORT = Path(__file__).resolve().parents[5] / "boerse-dashboard-github" / "TR" / "Transaktionsexport.csv"


@pytest.fixture(autouse=True)
def fixed_fx_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        portfolio_service,
        "get_eur_usd_rate",
        lambda: FxRate(pair="EUR/USD", rate=1.0, as_of=date(2026, 1, 1), source="test"),
    )


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


def test_portfolio_import_defaults_to_sync_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_upsert(rows, *, source: str, file_name: str, replace_open_positions: bool):
        captured["replace_open_positions"] = replace_open_positions
        return PortfolioImportResult(import_id="import-default-sync", rows_imported=len(rows))

    monkeypatch.setattr(portfolio_service.portfolio_repository, "upsert_imported_positions", fake_upsert)

    result = portfolio_service.import_portfolio_positions(
        PortfolioImportRequest(
            file_name="website-upload.csv",
            content="Ticker,Shares,Entry_Price\nAAPL,3,100\n",
            dry_run=False,
        )
    )

    assert result.ok is True
    assert captured["replace_open_positions"] is True


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
    monkeypatch.setattr(portfolio_service.portfolio_repository, "get_cash_balance", lambda: 0.0)
    monkeypatch.setattr(
        portfolio_service.prices_repository,
        "list_price_bars",
        lambda ticker, start_date=None: _price_bars(),
    )

    positions = portfolio_service.get_portfolio_positions()
    snapshot = portfolio_service.get_portfolio_snapshot()

    assert positions[0].atr_pct > 0
    assert positions[0].beta is None
    assert positions[0].beta_balancer_score is None
    assert positions[0].risk_contribution is None
    assert snapshot.portfolio_atr_pct == pytest.approx(positions[0].atr_pct)
    assert "Portfolio ATR" in {item.label for item in snapshot.kpis}
    assert "Portfolio Beta Balancer" in {item.label for item in snapshot.kpis}


def test_portfolio_weights_include_cash_and_do_not_overstate_risk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        PortfolioPositionRow(
            ticker="AAPL",
            name="Apple",
            shares=5,
            entry_price=80,
            current_price=100,
            currency="EUR",
            buy_date=date(2025, 1, 15),
            broker="Test",
            account="Main",
        )
    ]
    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_open_positions", lambda: rows)
    monkeypatch.setattr(portfolio_service.portfolio_repository, "get_cash_balance", lambda: 500.0)
    monkeypatch.setattr(
        portfolio_service.prices_repository,
        "list_price_bars",
        lambda ticker, start_date=None: _price_bars(),
    )

    position = portfolio_service.get_portfolio_positions()[0]

    assert position.market_value == pytest.approx(500.0)
    assert position.weight_pct == pytest.approx(50.0)


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


def test_buy_strength_overview_detects_recent_manual_and_imported_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    today = date.today()
    rows = [
        PortfolioPositionRow(
            ticker="NVDA",
            name="Nvidia",
            shares=4,
            entry_price=100,
            current_price=106,
            currency="USD",
            buy_date=date.fromordinal(today.toordinal() - 7),
            broker="Manual",
            account="Main",
        ),
        PortfolioPositionRow(
            ticker="MSFT",
            name="Microsoft",
            shares=2,
            entry_price=100,
            current_price=102,
            currency="USD",
            buy_date=today.replace(year=today.year - 1),
            broker="CSV",
            account="Main",
        ),
        PortfolioPositionRow(
            ticker="AMD",
            name="Advanced Micro Devices",
            shares=3,
            entry_price=100,
            current_price=103,
            currency="USD",
            buy_date=date.fromordinal(today.toordinal() - 35),
            broker="CSV",
            account="Main",
        ),
    ]

    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_open_positions", lambda: rows)
    monkeypatch.setattr(portfolio_service.prices_repository, "list_price_bars", lambda ticker, start_date=None: _buy_strength_price_bars(today=today, direction="up"))
    monkeypatch.setattr(portfolio_service.relative_strength_repository, "get_latest_rs_rating", lambda ticker: _rs_row(today=today, direction="up"))

    overview = portfolio_service.get_buy_strength_overview()

    assert [item.ticker for item in overview.items] == ["NVDA"]
    assert overview.window_days == 21
    assert overview.items[0].buy_date == rows[0].buy_date.isoformat()
    assert overview.items[0].age_days == 7
    assert overview.items[0].window_days == 21
    assert overview.items[0].latest_price_date is not None
    assert overview.items[0].data_status in {"fresh", "stale"}
    assert overview.items[0].checks_total == 7
    assert overview.items[0].warnings_total == 11
    assert overview.items[0].warnings_active >= 0

    six_week_overview = portfolio_service.get_buy_strength_overview(weeks=6)

    assert six_week_overview.window_days == 42
    assert {item.ticker for item in six_week_overview.items} == {"AMD", "NVDA"}


def test_buy_strength_assessment_flags_positive_purchase_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    today = date.today()
    buy_date = date.fromordinal(today.toordinal() - 7)
    row = PortfolioPositionRow(
        ticker="NVDA",
        name="Nvidia",
        shares=4,
        entry_price=100,
        current_price=106,
        currency="USD",
        buy_date=buy_date,
        broker="Manual",
        account="Main",
    )
    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_open_positions", lambda: [row])
    monkeypatch.setattr(portfolio_service.prices_repository, "list_price_bars", lambda ticker, start_date=None: _buy_strength_price_bars(today=today, direction="up"))
    monkeypatch.setattr(portfolio_service.relative_strength_repository, "get_latest_rs_rating", lambda ticker: _rs_row(today=today, direction="up"))

    assessment = portfolio_service.get_buy_strength_assessment("nvda")

    assert assessment.ticker == "NVDA"
    assert assessment.checks[0].label == "Unmittelbare Stärke nach Kauf"
    assert sum(check.passed for check in assessment.checks) >= 5
    assert assessment.warnings[0].category == "warning"
    assert assessment.status in {"stark", "ok", "watch"}


def test_buy_strength_assessment_flags_post_buy_weakness(monkeypatch: pytest.MonkeyPatch) -> None:
    today = date.today()
    buy_date = date.fromordinal(today.toordinal() - 7)
    row = PortfolioPositionRow(
        ticker="WEAK",
        name="Weak Stock",
        shares=4,
        entry_price=100,
        current_price=91,
        currency="USD",
        buy_date=buy_date,
        broker="Manual",
        account="Main",
    )
    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_open_positions", lambda: [row])
    monkeypatch.setattr(portfolio_service.prices_repository, "list_price_bars", lambda ticker, start_date=None: _buy_strength_price_bars(today=today, direction="down"))
    monkeypatch.setattr(portfolio_service.relative_strength_repository, "get_latest_rs_rating", lambda ticker: _rs_row(today=today, direction="down"))

    assessment = portfolio_service.get_buy_strength_assessment("WEAK")

    active_warning_keys = {check.key for check in assessment.warnings if not check.passed}
    assert "three_lower_lows" in active_warning_keys
    assert "rs_declines" in active_warning_keys
    assert assessment.status in {"watch", "risk"}


def test_trade_republic_stop_price_override_stays_usd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        portfolio_service,
        "get_eur_usd_rate",
        lambda: FxRate(pair="EUR/USD", rate=1.1, as_of=date(2026, 1, 1), source="test"),
    )
    row = PortfolioPositionRow(
        ticker="NVDA",
        name="Nvidia",
        shares=2,
        entry_price=100,
        current_price=120,
        currency="EUR",
        buy_date=date(2026, 1, 1),
        stop_pct=7,
        stop_price=200,
        broker="Trade Republic",
        account="Main",
        current_price_source="position_entry",
    )

    normalized = portfolio_service._normalize_trade_republic_row_to_usd(row)

    assert normalized.currency == "USD"
    assert normalized.entry_price == pytest.approx(110)
    assert normalized.current_price == pytest.approx(132)
    assert normalized.stop_price == 200


def test_trade_republic_cached_listing_price_is_converted_from_quote_currency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        portfolio_service,
        "get_eur_usd_rate",
        lambda: FxRate(pair="EUR/USD", rate=1.1, as_of=date(2026, 1, 1), source="test"),
    )
    monkeypatch.setattr(
        portfolio_service,
        "currency_to_usd",
        lambda value, currency: float(value) * 1.1 if currency == "EUR" else float(value),
    )
    row = PortfolioPositionRow(
        ticker="SIE.DE",
        name="Siemens",
        shares=2,
        entry_price=100,
        current_price=120,
        currency="EUR",
        buy_date=date(2026, 1, 1),
        broker="Trade Republic",
        account="Main",
        current_price_source="price_cache",
    )

    normalized = portfolio_service._normalize_trade_republic_row_to_usd(row)

    assert normalized.entry_price == pytest.approx(110)
    assert normalized.current_price == pytest.approx(132)
    assert normalized.currency == "USD"


def test_trade_republic_usd_position_converts_foreign_cached_listing_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        portfolio_service,
        "currency_to_usd",
        lambda value, currency: float(value) * 0.128 if currency == "HKD" else float(value),
    )
    row = PortfolioPositionRow(
        ticker="2318.HK",
        name="Ping An Insurance",
        shares=100,
        entry_price=6.85,
        current_price=53.60,
        currency="USD",
        buy_date=date(2026, 1, 1),
        broker="Trade Republic",
        account="Main",
        current_price_source="price_cache",
    )

    normalized = portfolio_service._normalize_trade_republic_row_to_usd(row)

    assert normalized.entry_price == pytest.approx(6.85)
    assert normalized.current_price == pytest.approx(6.8608)
    assert normalized.currency == "USD"


def test_beta_falls_back_to_aligned_cached_returns() -> None:
    start = date(2026, 1, 1)
    benchmark_close = 100.0
    asset_close = 50.0
    benchmark_rows: list[MarketOhlcvPoint] = []
    asset_rows: list[MarketOhlcvPoint] = []
    daily_returns = [-0.02, 0.01, 0.005, -0.007, 0.015, -0.003] * 7
    for offset, benchmark_return in enumerate([0.0, *daily_returns]):
        if offset:
            benchmark_close *= 1 + benchmark_return
            asset_close *= 1 + benchmark_return * 1.5
        bar_date = start + timedelta(days=offset)
        benchmark_rows.append(
            MarketOhlcvPoint("SPY", bar_date, benchmark_close, benchmark_close, benchmark_close, benchmark_close, 1)
        )
        asset_rows.append(
            MarketOhlcvPoint("TEST", bar_date, asset_close, asset_close, asset_close, asset_close, 1)
        )

    beta = portfolio_service._beta_from_price_rows(asset_rows, benchmark_rows)

    assert beta == pytest.approx(1.5, abs=0.02)


def test_beta_fallback_requires_sufficient_aligned_history() -> None:
    row = MarketOhlcvPoint("TEST", date(2026, 1, 1), 100, 100, 100, 100, 1)

    assert portfolio_service._beta_from_price_rows([row], [row]) is None


def test_after_hours_portfolio_converts_yahoo_quote_currency_to_usd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = PortfolioPositionRow(
        ticker="SIE.DE",
        name="Siemens",
        shares=2,
        entry_price=100,
        current_price=130,
        currency="USD",
        buy_date=date(2026, 1, 1),
        broker="Test",
        account="Main",
        current_price_source="price_cache",
    )
    quote = FetchedAfterHoursQuote(
        ticker="SIE.DE",
        regular_price=120,
        after_hours_price=122,
        after_hours_change=2,
        after_hours_change_pct=1.6667,
        currency="EUR",
        market_state="POST",
        source="test",
        fetched_at=datetime(2026, 7, 23, tzinfo=UTC),
    )
    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_open_positions", lambda: [row])
    monkeypatch.setattr(portfolio_service, "fetch_after_hours_quotes", lambda tickers: {"SIE.DE": quote})
    monkeypatch.setattr(
        portfolio_service,
        "get_currency_usd_rate",
        lambda currency: FxRate(
            pair=f"{currency}/USD",
            rate=1.1,
            as_of=date(2026, 7, 23),
            source="test",
        ),
    )

    result = portfolio_service.get_portfolio_after_hours()

    assert result.positions[0].regular_price == pytest.approx(132)
    assert result.positions[0].after_hours_price == pytest.approx(134.2)
    assert result.positions[0].after_hours_value_change == pytest.approx(4.4)
    assert result.total_after_hours_change == pytest.approx(4.4)


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


def test_trade_republic_import_defaults_to_sync_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_import(*, transactions, positions, mappings, file_name: str, replace_open_positions: bool):
        captured["replace_open_positions"] = replace_open_positions
        return TradeRepublicImportResult(
            import_id="tr-import-default-sync",
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
        )
    )

    assert result.ok is True
    assert captured["replace_open_positions"] is True


def test_trade_republic_sync_save_requires_open_position_mappings(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_import(**kwargs):
        nonlocal called
        called = True
        return TradeRepublicImportResult(import_id="should-not-save", rows_imported=0, transactions_imported=0)

    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_isin_mappings", lambda: {})
    monkeypatch.setattr(portfolio_service.portfolio_repository, "import_trade_republic_transactions", fake_import)
    content = (
        "date,datetime,type,asset_class,name,symbol,shares,price,currency,amount,fee,tax\n"
        "2025-01-02,2025-01-02T10:00:00Z,BUY,STOCK,Unknown Corp,US0000000000,10,100,USD,-1000,0,0\n"
    )

    result = portfolio_service.import_trade_republic_transaction_export(
        TradeRepublicTransactionImportRequest(
            file_name="tr-missing-mapping.csv",
            content=content,
            dry_run=False,
            replace_open_positions=True,
        )
    )

    assert result.ok is False
    assert called is False
    assert "US0000000000" in result.errors[0]


def test_trade_republic_import_converts_eur_prices_to_usd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(portfolio_service.portfolio_repository, "list_isin_mappings", lambda: {})
    monkeypatch.setattr(
        portfolio_service,
        "get_eur_usd_rate",
        lambda: FxRate(pair="EUR/USD", rate=1.1, as_of=date(2026, 1, 1), source="test"),
    )
    content = (
        "date,datetime,type,asset_class,name,symbol,shares,price,currency,amount,fee,tax\n"
        "2025-01-02,2025-01-02T10:00:00Z,BUY,STOCK,NVIDIA,US67066G1040,10,100,EUR,-1000,0,0\n"
    )

    result = portfolio_service.import_trade_republic_transaction_export(
        TradeRepublicTransactionImportRequest(
            file_name="tr-eur.csv",
            content=content,
            dry_run=True,
            replace_open_positions=False,
        )
    )

    assert result.ok is True
    assert result.positions[0].ticker == "NVDA"
    assert result.positions[0].entry_price == pytest.approx(110.0)
    assert result.positions[0].currency == "USD"
    assert any("EUR/USD 1.1000" in warning for warning in result.warnings)


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


def _buy_strength_price_bars(*, today: date, direction: str):
    start = today.fromordinal(today.toordinal() - 34)
    bars = []
    for offset in range(35):
        day = start.fromordinal(start.toordinal() + offset)
        base = 100 + offset * 0.2
        if offset >= 27:
            post_offset = offset - 27
            if direction == "up":
                open_value = 101 + post_offset
                close_value = open_value + 1.2
                high_value = close_value + 0.4
                low_value = open_value - 0.8
                volume = 1_000_000 + post_offset * 25_000
            else:
                open_value = 100 - post_offset * 1.2
                close_value = open_value - 1.0
                high_value = open_value + 0.3
                low_value = close_value - 0.7
                volume = 1_200_000 + post_offset * 80_000
        else:
            open_value = base
            close_value = base + 0.3
            high_value = base + 0.7
            low_value = base - 0.7
            volume = 900_000
        bars.append(
            SimpleNamespace(
                date=day,
                open=open_value,
                high=high_value,
                low=low_value,
                close=close_value,
                adj_close=close_value,
                volume=volume,
            )
        )
    return bars


def _rs_row(*, today: date, direction: str):
    start = today.fromordinal(today.toordinal() - 34)
    history = []
    for offset in range(35):
        value = 80 + offset * 0.4 if direction == "up" else 100 - offset * 0.6
        history.append(
            {
                "date": start.fromordinal(start.toordinal() + offset).isoformat(),
                "rs": value,
                "rs_ema21": value - 1 if direction == "up" else value + 1,
                "rs_ema50": value - 2 if direction == "up" else value + 2,
            }
        )
    return SimpleNamespace(metadata_json={"rs_history": history})
