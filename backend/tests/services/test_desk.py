from copy import deepcopy
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domain.desk import (
    Alert,
    ImportRequest,
    Plan,
    PlanStage,
    Watchlist,
    WatchTransfer,
    curve_statistics,
    import_rows,
    in_quiet_hours,
    merge_import,
    money_weighted_return,
    plan_numbers,
)
from app.repositories.desk import DeskConflict, DeskUnavailable
from app.services import desk


@pytest.fixture
def memory(monkeypatch):
    stored = dict(
        revision=0,
        watchlists=[dict(id="default", name="Favoriten", items=[])],
        plans=[],
        alerts=[],
        history=[],
        events=[],
        accounts=[],
    )

    def transact(operation=None, *, revision=None):
        if operation is None:
            return deepcopy(stored)
        if revision is not None and revision != stored["revision"]:
            raise DeskConflict("Konflikt")
        candidate = deepcopy(stored)
        result = operation(candidate)
        candidate["revision"] += 1
        stored.clear()
        stored.update(candidate)
        return deepcopy(result if result is not None else stored)

    monkeypatch.setattr(desk.repository, "transact", transact)
    return stored


@pytest.fixture
def plan():
    return Plan(
        ticker="NVDA",
        entry=100,
        stop=90,
        risk_pct=1,
        fees=2,
        thesis="Ausbruch mit Volumen",
        invalidation="Unter 90 USD",
    )


def test_planning_converts_risk_and_cash_in_the_same_direction(plan):
    result = plan_numbers(plan, total=10000, cash=10000, fx=1 / 1.1, existing_risk=100)
    assert result["shares"] == 10
    assert result["planned_risk"] == 92.73
    assert result["cash_required"] == 910.91
    assert result["portfolio_risk_pct"] == pytest.approx(1.9273)


def test_cash_and_fees_limit_a_plan_and_missing_stop_risk_stays_unknown(plan):
    result = plan_numbers(plan, total=10000, cash=202, fx=1)
    assert result["shares"] == 2
    assert result["limited_by"] == "cash"
    assert result["portfolio_risk_pct"] is None
    assert plan_numbers(plan, total=10000, cash=1, fx=1)["shares"] == 0


@pytest.mark.parametrize(
    "updates",
    [{"stop": 100}, {"target": 90}, {"entry": float("nan")}, {"risk_pct": 10}, {"thesis": " "}],
)
def test_invalid_plans_are_rejected(plan, updates):
    with pytest.raises(ValidationError):
        Plan(**(plan.model_dump() | updates))


@pytest.mark.parametrize(
    "hour,expected", [(21, False), (22, True), (0, True), (6, True), (7, False)]
)
def test_quiet_hours_cross_midnight(hour, expected):
    assert in_quiet_hours(datetime(2026, 10, 22, hour), "22:00", "07:00") is expected


def test_equal_quiet_boundaries_disable_quiet_hours():
    assert not in_quiet_hours(datetime(2026, 10, 22, 12), "00:00", "00:00")


def test_csv_preview_deduplicates_and_rejects_changed_ids_and_oversells():
    csv = "date,type,ticker,shares,price,currency,amount,external_id\n2026-01-02,deposit,,,,EUR,1000,cash-1\n2026-01-05,buy,SAP.DE,2,100,EUR,,buy-1\n"
    rows = import_rows(csv)
    merged, duplicates = merge_import(rows, rows)
    assert len(merged) == 2 and duplicates == 2
    with pytest.raises(ValueError, match="anderem Inhalt"):
        merge_import(rows, import_rows(csv.replace(",2,100,", ",3,100,")))
    with pytest.raises(ValueError, match="Bestand"):
        merge_import([], import_rows(csv.replace(",buy,", ",sell,")))


@pytest.mark.parametrize("value", ["nan", "inf", "-1"])
def test_csv_invalid_numbers_never_reach_a_ledger(value):
    with pytest.raises(ValueError, match="Zeile 2"):
        import_rows(f"date,type,currency,amount\n2026-01-02,deposit,EUR,{value}\n")


def test_xirr_handles_cash_timing_and_ambiguous_roots():
    first, middle, last = date(2025, 1, 1), date(2025, 7, 2), date(2026, 1, 1)
    assert money_weighted_return([(first, -1000), (last, 1100)]) == pytest.approx(10)
    terminal = 1100 + 1000 * 1.1 ** ((last - middle).days / 365)
    assert money_weighted_return(
        [(first, -1000), (middle, -1000), (last, terminal)]
    ) == pytest.approx(10)
    assert (
        money_weighted_return(
            [(date(2023, 1, 1), -100), (date(2024, 1, 1), 230), (date(2024, 12, 31), -132)]
        )
        is None
    )
    assert money_weighted_return([(first, 100), (last, 110)]) is None


def test_performance_never_labels_a_simulation_or_a_gap_as_complete_history():
    points = [{"portfolio_index": value} for value in [100, 120, 90, 110]]
    result = curve_statistics(points, historical=True)
    assert result["twr_pct"] == pytest.approx(10)
    assert result["max_drawdown_pct"] == pytest.approx(-25)
    assert curve_statistics(points, historical=False)["twr_pct"] is None
    assert (
        curve_statistics([*points, {"portfolio_index": None}], historical=True)["max_drawdown_pct"]
        is None
    )


def test_named_lists_keep_notes_and_bulk_moves_are_atomic(memory):
    desk.save(
        "watchlists",
        Watchlist(
            name="Kandidaten", items=[dict(ticker="NVDA", note="Ausbruch", tags=["Wachstum"])]
        ),
        revision=0,
    )
    source = memory["watchlists"][1]["id"]
    desk.transfer_watchlist(
        WatchTransfer(source=source, target="default", tickers=["NVDA"], move=True), revision=1
    )
    assert memory["watchlists"][0]["items"][0]["note"] == "Ausbruch"
    assert memory["watchlists"][1]["items"] == []
    with pytest.raises(DeskConflict):
        desk.save("watchlists", Watchlist(name="Stale"), revision=0)
    assert len(memory["watchlists"]) == 2


def test_account_import_requires_the_same_preview_and_cannot_double_book(memory):
    memory["accounts"] = [dict(id="test", name="Zweitdepot", currency="EUR", transactions=[])]
    content = "date,type,currency,amount,external_id\n2026-01-02,deposit,EUR,1000,cash-1\n"
    preview = desk.import_account("test", ImportRequest(csv=content), revision=0)
    assert not memory["accounts"][0]["transactions"]
    with pytest.raises(ValueError, match="erneut prüfen"):
        desk.import_account(
            "test", ImportRequest(csv=content, commit=True, preview_hash="bad"), revision=0
        )
    assert memory["revision"] == 0
    desk.import_account(
        "test",
        ImportRequest(csv=content, commit=True, preview_hash=preview["preview_hash"]),
        revision=0,
    )
    again = desk.import_account("test", ImportRequest(csv=content), revision=1)
    assert again["duplicates"] == 1 and again["added"] == 0
    assert desk.state()["accounts"][0]["transaction_count"] == 1
    assert "transactions" not in desk.state()["accounts"][0]


def test_fx_identity_works_without_provider_and_stale_fx_is_blocked(monkeypatch):
    monkeypatch.setattr(
        desk, "completed_us_market_session", lambda: SimpleNamespace(date=date(2026, 10, 21))
    )
    monkeypatch.setattr(desk, "_latest_cached_fx_rate", lambda *a, **kw: None)
    assert desk.fx_quote("EUR", "EUR")["rate"] == 1
    with pytest.raises(ValueError, match="Wechselkurs"):
        desk.fx_quote("EUR", "USD")
    monkeypatch.setattr(
        desk,
        "_latest_cached_fx_rate",
        lambda *a, **kw: SimpleNamespace(rate=1.1, as_of=date(2026, 10, 21)),
    )
    assert desk.fx_quote("EUR", "USD")["rate"] == pytest.approx(1.1)
    assert desk.fx_quote("USD", "EUR")["rate"] == pytest.approx(1 / 1.1)


def test_immutable_plan_snapshot_and_changed_preview(memory, monkeypatch, plan):
    monkeypatch.setattr(
        desk, "account", lambda _: dict(currency="EUR", total_value=10000, cash=10000, positions=[])
    )
    monkeypatch.setattr(desk, "fx_quote", lambda *a: dict(rate=1 / 1.1, as_of="2026-10-21"))
    monkeypatch.setattr(
        desk,
        "capture",
        lambda _: dict(as_of="2026-10-21", scores={"overall": 77}, calculation={"version": "v2"}),
    )
    preview = desk.preview_plan(plan)
    desk.create_plan(plan, revision=0, preview_hash=preview["preview_hash"])
    plan_id = memory["plans"][0]["id"]
    desk.stage_plan(
        plan_id, PlanStage(stage="purchased", note="Ausführung im Depot erfasst"), revision=1
    )
    assert memory["plans"][0]["preview"]["assessment"]["scores"]["overall"] == 77
    assert len(memory["plans"][0]["history"]) == 2
    monkeypatch.setattr(desk, "capture", lambda _: dict(as_of="2026-10-22", scores={"overall": 40}))
    with pytest.raises(DeskConflict, match="erneut berechnen"):
        desk.create_plan(plan, revision=2, preview_hash=preview["preview_hash"])


def test_existing_portfolio_contract_uses_account_cash_and_base_market_values(monkeypatch):
    from app.services import portfolio

    snapshot = dict(
        currency="EUR",
        cash_balance=500,
        total_value=1500,
        data_quality_status="trusted",
        positions=[dict(ticker="NVDA", currency="USD", market_value=1100, base_market_value=1000)],
    )
    monkeypatch.setattr(
        portfolio,
        "get_portfolio_snapshot",
        lambda: SimpleNamespace(model_dump=lambda **kw: snapshot),
    )
    result = desk.account("main")
    assert result["cash"] == 500
    assert result["positions"][0]["market_value"] == 1000
    assert result["positions"][0]["currency"] == "USD"


def test_preview_ignores_response_time_but_captures_changes_to_account_basis(
    memory, monkeypatch, plan
):
    depot = dict(
        currency="EUR", total_value=10000, cash=10000, positions=[], as_of="2026-10-22T10:00:00Z"
    )
    monkeypatch.setattr(desk, "account", lambda _: dict(depot))
    monkeypatch.setattr(desk, "fx_quote", lambda *a: dict(rate=1, as_of="2026-10-21"))
    monkeypatch.setattr(desk, "capture", lambda _: dict(as_of="2026-10-21", scores={"overall": 77}))
    preview = desk.preview_plan(plan)
    depot["as_of"] = "2026-10-22T10:01:00Z"
    assert desk.preview_plan(plan)["preview_hash"] == preview["preview_hash"]
    desk.create_plan(plan, revision=0, preview_hash=preview["preview_hash"])
    assert memory["plans"][0]["preview"]["account_basis"]["cash"] == 10000
    depot["cash"] = 9999
    with pytest.raises(DeskConflict):
        desk.create_plan(plan, revision=1, preview_hash=preview["preview_hash"])


def test_alert_cooldown_quiet_hours_and_acknowledgement(memory, monkeypatch):
    rule = Alert(name="Kurs beobachten", ticker="NVDA", kind="price_above", threshold=100)
    desk.save("alerts", rule, revision=0)
    monkeypatch.setattr(desk, "observe", lambda rule: (True, "Kurs 110", "2026-10-21"))
    desk.evaluate_alerts(now=datetime(2026, 10, 21, 23, tzinfo=UTC))
    assert memory["history"] == []
    assert memory["alerts"][0]["check_status"] == "quiet"
    desk.evaluate_alerts(now=datetime(2026, 10, 22, 10, tzinfo=UTC))
    desk.evaluate_alerts(now=datetime(2026, 10, 22, 10, 5, tzinfo=UTC))
    assert len(memory["history"]) == 1
    desk.acknowledge(memory["history"][0]["id"], revision=memory["revision"])
    assert memory["history"][0]["acknowledged_at"]
    monkeypatch.setattr(
        desk, "observe", lambda rule: (_ for _ in ()).throw(ValueError("Kurs fehlt"))
    )
    desk.evaluate_alerts(now=datetime(2026, 10, 23, 10, tzinfo=UTC))
    assert len(memory["history"]) == 1
    assert memory["alerts"][0]["check_status"] == "missing"


def test_private_api_returns_conflicts_and_unavailability_without_false_success(
    memory, monkeypatch
):
    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/api/v1/desk/watchlists?revision=0", json=dict(name="Earnings", items=[])
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/v1/desk/watchlists?revision=0", json=dict(name="Stale", items=[])
        ).status_code
        == 409
    )

    def unavailable(*a, **kw):
        raise DeskUnavailable("Database down")

    monkeypatch.setattr(desk.repository, "transact", unavailable)
    assert client.get("/api/v1/desk/state").status_code == 503


@pytest.mark.parametrize("missing_day", [False, True])
@pytest.mark.parametrize("quote_basis", ["unadjusted", "split_adjusted", "legacy_unknown"])
def test_additional_account_performance_adjusts_deposits_fees_and_splits(
    memory, monkeypatch, missing_day, quote_basis
):
    import pandas as pd
    from app.services import market_calendar

    days = [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    content = "date,type,ticker,shares,price,currency,fees,amount,external_id\n2026-01-02,deposit,,,,USD,0,1000,d1\n2026-01-02,buy,NVDA,5,100,USD,0,,b1\n2026-01-05,deposit,,,,USD,0,1000,d2\n2026-01-06,split,NVDA,10,0,USD,0,,sp1\n2026-01-07,sell,NVDA,2,55,USD,2,,s1\n"
    rows, _ = merge_import([], import_rows(content))
    memory["accounts"] = [dict(id="extra", name="Zweitdepot", currency="USD", transactions=rows)]
    histories = {
        "NVDA": [
            SimpleNamespace(
                date=stamp,
                close=price / (2 if quote_basis == "split_adjusted" and stamp < days[2] else 1),
                source="fixture" if quote_basis == "unadjusted" else "yfinance",
                split_adjustment_factor=(2 if stamp < days[2] else 1)
                if quote_basis == "split_adjusted"
                else None,
            )
            for stamp, price in zip(days, [100, 110, 55, 55])
            if not missing_day or stamp != days[1]
        ],
        "SPY": [
            SimpleNamespace(date=stamp, close=price)
            for stamp, price in zip(days, [500, 520, 510, 530])
        ],
    }
    monkeypatch.setattr(desk.prices, "list_price_bars_for_tickers", lambda *a, **kw: histories)
    monkeypatch.setattr(desk, "completed_us_market_session", lambda: SimpleNamespace(date=days[-1]))
    monkeypatch.setattr(
        market_calendar,
        "common_market_sessions",
        lambda ticker, benchmark, start, end: pd.DatetimeIndex(
            [d for d in days if start <= d <= end]
        ),
    )
    result = desk.performance(start=days[0], benchmark="SPY", account_id="extra")
    if missing_day or quote_basis == "legacy_unknown":
        assert result["twr_pct"] is None
        assert result["period_result"] is None
        assert not result["complete"]
    else:
        assert result["twr_pct"] == pytest.approx((1.05 * 2048 / 2050 - 1) * 100)
        assert result["period_result"] == 48
        assert result["external_flow"] == 1000
        assert result["benchmark_return_pct"] == pytest.approx(6)
        assert result["mwr_annual_pct"] is not None


@pytest.mark.parametrize("enabled,dry_run", [(False, False), (True, True), (True, False)])
def test_notification_worker_claims_once_and_honours_global_controls(
    memory, monkeypatch, enabled, dry_run
):
    from app import core_config
    from app.services import settings
    from app.workers.tasks import check_workspace_alerts as worker, pushover_test

    memory["alerts"] = [
        dict(id="rule", enabled=True, push=True, quiet_start="00:00", quiet_end="00:00")
    ]
    memory["history"] = [
        dict(
            id=str(i),
            rule_id="rule",
            push_status="pending",
            name="Test",
            ticker="NVDA",
            detail="Schwelle erreicht",
            as_of="2026-10-21",
        )
        for i in range(7)
    ]
    monkeypatch.setattr(desk, "evaluate_alerts", desk.state)
    monkeypatch.setattr(
        core_config,
        "get_settings",
        lambda: SimpleNamespace(
            pushover_dry_run=False, pushover_app_token="test-token", pushover_user_key="test-user"
        ),
    )
    monkeypatch.setattr(
        settings, "get_app_settings", lambda: SimpleNamespace(pushover_enabled=enabled)
    )
    monkeypatch.setattr(settings, "get_runtime_config_bool", lambda *a: dry_run)
    monkeypatch.setattr(settings, "get_runtime_config_value", lambda *a: "")
    deliveries = []
    monkeypatch.setattr(
        pushover_test, "_send_pushover_message", lambda **kw: deliveries.append(kw) or {"status": 1}
    )
    result = worker.check_workspace_alerts.run()
    expected = 5 if enabled and not dry_run else 0
    assert result["deliveries"] == expected == len(deliveries)
    if expected:
        assert [row["push_status"] for row in memory["history"]].count("sent") == 5
        worker.check_workspace_alerts.run()
        assert len(deliveries) == 7
        worker.check_workspace_alerts.run()
        assert len(deliveries) == 7
    else:
        assert all(row["push_status"] == "skipped" for row in memory["history"])


@pytest.mark.parametrize(
    "content",
    [
        "date,type,currency,amount\n2026-01-02,deposit\n",
        "date,type,currency,amount\n2026-01-02,deposit,EUR,1,extra\n",
        "date,type,currency,amount,amount\n2026-01-02,deposit,EUR,1,2\n",
    ],
)
def test_malformed_csv_is_rejected_with_validation_error(content):
    with pytest.raises(ValueError):
        import_rows(content)


def test_calendar_does_not_require_portfolio_quotes_or_fx(memory, monkeypatch):
    from app.repositories import portfolio
    from app.domain.desk import Event

    today = datetime.now(desk.ZoneInfo("Europe/Berlin")).date()
    memory["events"] = [
        dict(id="own", **Event(title="Eigene Prüfung", date=today).model_dump(mode="json"))
    ]
    memory["accounts"] = [
        dict(
            id="extra",
            transactions=import_rows(
                f"date,type,ticker,shares,price,currency\n{today},buy,SAP.DE,2,100,EUR\n"
            ),
        )
    ]
    monkeypatch.setattr(portfolio, "list_open_positions", lambda: [SimpleNamespace(ticker="NVDA")])
    requested = []
    monkeypatch.setattr(
        desk.earnings,
        "upcoming_earnings_events",
        lambda tickers, **kw: requested.extend(tickers) or [],
    )
    monkeypatch.setattr(
        desk,
        "account",
        lambda *a, **kw: pytest.fail("Calendar must not require account valuations"),
    )
    result = desk.calendar()
    assert requested == ["NVDA", "SAP.DE"]
    assert result["rows"][0]["title"] == "Eigene Prüfung"

    def unavailable():
        raise portfolio.PortfolioRepositoryUnavailable("offline")

    monkeypatch.setattr(portfolio, "list_open_positions", unavailable)
    result = desk.calendar()
    assert result["rows"][0]["id"] == "own"
    assert result["coverage_note"]


def test_rs_alarm_uses_selected_source_and_rejects_stale_observations(monkeypatch):
    from app.services import relative_strength

    monkeypatch.setattr(
        desk, "completed_us_market_session", lambda: SimpleNamespace(date=date(2026, 10, 21))
    )
    monkeypatch.setattr(relative_strength, "configured_rs_source", lambda: "minervini")
    requested = []
    stamp = date(2026, 10, 21)

    def observation(ticker, *, source):
        requested.append((ticker, source))
        return SimpleNamespace(date=stamp, rating=70)

    monkeypatch.setattr(desk.relative_strength, "get_latest_rs_rating", observation)
    rule = Alert(name="Stärke", ticker="NVDA", kind="rs_below", threshold=80).model_dump()
    assert desk.observe(rule)[0]
    assert requested == [("NVDA", "minervini")]
    stamp = date(2026, 10, 20)
    with pytest.raises(ValueError, match="RS-Rating fehlt"):
        desk.observe(rule)
