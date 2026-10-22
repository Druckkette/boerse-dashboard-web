from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.domain.desk import (
    Account,
    Alert,
    Event,
    ImportRequest,
    Plan,
    PlanStage,
    Watchlist,
    WatchTransfer,
)
from app.repositories.desk import DeskConflict, DeskUnavailable
from app.services import desk

router = APIRouter()


def run(operation):
    try:
        return operation()
    except DeskConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (DeskUnavailable, RuntimeError) as exc:
        raise HTTPException(
            status_code=503, detail="Daten derzeit nicht verfügbar. Bitte erneut versuchen."
        ) from exc


@router.get("/state")
def read_state():
    return run(desk.state)


@router.get("/fx")
def fx(source: str = Query(pattern=r"^[A-Z]{3}$"), target: str = Query(pattern=r"^[A-Z]{3}$")):
    return run(lambda: desk.fx_quote(source, target))


@router.post("/watchlists")
def add_watchlist(payload: Watchlist, revision: int = Query(ge=0)):
    return run(lambda: desk.save("watchlists", payload, revision=revision))


@router.put("/watchlists/{item_id}")
def edit_watchlist(item_id: str, payload: Watchlist, revision: int = Query(ge=0)):
    return run(lambda: desk.save("watchlists", payload, item_id=item_id, revision=revision))


@router.post("/watchlists/transfer")
def transfer_watchlist(payload: WatchTransfer, revision: int = Query(ge=0)):
    return run(lambda: desk.transfer_watchlist(payload, revision=revision))


@router.post("/plans/preview")
def preview(payload: Plan):
    return run(lambda: desk.preview_plan(payload))


@router.post("/plans")
def add_plan(
    payload: Plan, revision: int = Query(ge=0), preview_hash: str = Query(pattern=r"^[a-f0-9]{64}$")
):
    return run(lambda: desk.create_plan(payload, revision=revision, preview_hash=preview_hash))


@router.post("/plans/{item_id}/stage")
def stage(item_id: str, payload: PlanStage, revision: int = Query(ge=0)):
    return run(lambda: desk.stage_plan(item_id, payload, revision=revision))


@router.post("/alerts")
def add_alert(payload: Alert, revision: int = Query(ge=0)):
    return run(lambda: desk.save("alerts", payload, revision=revision))


@router.put("/alerts/{item_id}")
def edit_alert(item_id: str, payload: Alert, revision: int = Query(ge=0)):
    return run(lambda: desk.save("alerts", payload, item_id=item_id, revision=revision))


@router.post("/alerts/check")
def check_alerts():
    return run(desk.evaluate_alerts)


@router.post("/history/{item_id}/acknowledge")
def acknowledge(item_id: str, revision: int = Query(ge=0)):
    return run(lambda: desk.acknowledge(item_id, revision=revision))


@router.get("/legacy-alerts")
def legacy_alerts():
    from app.repositories.settings import read_pushover_delivery_log

    return run(lambda: {"entries": read_pushover_delivery_log()})


@router.post("/events")
def add_event(payload: Event, revision: int = Query(ge=0)):
    return run(lambda: desk.save("events", payload, revision=revision))


@router.get("/calendar")
def calendar(
    days: int = Query(default=35, ge=1, le=365),
    scope: Literal["all", "portfolio", "watchlist"] = "all",
):
    return run(lambda: desk.calendar(days=days, scope=scope))


@router.post("/accounts")
def add_account(payload: Account, revision: int = Query(ge=0)):
    return run(lambda: desk.save("accounts", payload, revision=revision))


@router.get("/accounts/overview")
def accounts_overview():
    return run(desk.account_overview)


@router.get("/accounts/{account_id}")
def account(account_id: str):
    return run(lambda: desk.account(account_id))


@router.post("/accounts/{account_id}/import")
def import_account(account_id: str, payload: ImportRequest, revision: int = Query(ge=0)):
    return run(lambda: desk.import_account(account_id, payload, revision=revision))


@router.get("/performance")
def performance(
    start: date,
    benchmark: Literal["SPY", "QQQ", "IWM", "RSP", "^GSPC"] = "SPY",
    account_id: str = Query(default="main", pattern=r"^[a-z0-9]{1,40}$"),
):
    if not date(1970, 1, 1) <= start <= date.today():
        raise HTTPException(
            status_code=422, detail="Startdatum muss zwischen 1970 und heute liegen."
        )
    return run(lambda: desk.performance(start=start, benchmark=benchmark, account_id=account_id))


@router.delete("/{collection}/{item_id}")
def remove(
    collection: Literal["watchlists", "alerts", "events", "accounts"],
    item_id: str,
    revision: int = Query(ge=0),
):
    return run(lambda: desk.remove(collection, item_id, revision=revision))
