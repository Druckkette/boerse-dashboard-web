"""Postgres owns pending work; broker messages only wake the worker."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import RefreshWorkItem
from app.db.session import SessionLocal


@dataclass(frozen=True)
class WorkRequest:
    ticker: str
    data_group: str
    revision: str
    due_at: datetime
    priority: int = 50
    payload: dict | None = None


def enqueue(requests: list[WorkRequest]) -> int:
    with SessionLocal() as db:
        unique = {f"{r.data_group}:{r.ticker}": r for r in requests}
        items = list(unique.items())
        for offset in range(0, len(items), 500):
            statement = insert(RefreshWorkItem).values([dict(
                key=key, ticker=r.ticker, data_group=r.data_group, revision=r.revision,
                due_at=r.due_at, priority=r.priority, status="queued", attempts=0,
                payload_json=r.payload or {}, result_json={}, error="",
            ) for key, r in items[offset:offset + 500]])
            new = statement.excluded
            db.execute(statement.on_conflict_do_update(index_elements=["key"], set_={
                "revision": new.revision, "payload_json": new.payload_json,
                "due_at": new.due_at, "priority": new.priority, "attempts": 0,
                "result_json": {},
                "status": case((RefreshWorkItem.status == "running", "running"), else_="queued"),
            }, where=(new.revision != "baseline") & (new.revision > RefreshWorkItem.revision)))
        db.commit()
    return len(requests)


def claim(*, allow_sec: bool = False, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(UTC)
    with SessionLocal() as db:
        query = select(RefreshWorkItem).where(
            RefreshWorkItem.due_at <= now,
            or_(RefreshWorkItem.status != "running", RefreshWorkItem.lease_until < now),
        )
        if not allow_sec:
            query = query.where(RefreshWorkItem.data_group != "sec13f")
        # Ageing helps overdue work, but cannot outrank newly due portfolio/earnings work.
        age_hours = func.extract("epoch", now - RefreshWorkItem.due_at) / 3600
        score = RefreshWorkItem.priority - func.least(age_hours, 20)
        row = db.scalar(query.order_by(score, RefreshWorkItem.due_at, RefreshWorkItem.key)
                        .with_for_update(skip_locked=True).limit(1))
        if row is None:
            return None
        row.status = "running"
        row.lease_token = str(uuid4())
        row.lease_until = now + timedelta(minutes=5)
        row.attempts += 1
        item = {"key": row.key, "ticker": row.ticker, "data_group": row.data_group,
                "revision": row.revision, "priority": row.priority,
                "token": row.lease_token, "attempts": row.attempts,
                "payload": dict(row.payload_json), "previous_result": dict(row.result_json)}
        db.commit()
        return item


def claim_more(data_group: str, *, limit: int, now: datetime | None = None) -> list[dict]:
    """Lease more due items of one group for a bounded batch."""
    if limit <= 0:
        return []
    now = now or datetime.now(UTC)
    with SessionLocal() as db:
        rows = db.scalars(
            select(RefreshWorkItem).where(
                RefreshWorkItem.data_group == data_group,
                RefreshWorkItem.due_at <= now,
                or_(RefreshWorkItem.status != "running", RefreshWorkItem.lease_until < now),
            ).order_by(RefreshWorkItem.priority, RefreshWorkItem.due_at, RefreshWorkItem.key)
            .with_for_update(skip_locked=True).limit(limit)
        ).all()
        items = []
        for row in rows:
            row.status = "running"
            row.lease_token = str(uuid4())
            row.lease_until = now + timedelta(minutes=5)
            row.attempts += 1
            items.append({"key": row.key, "ticker": row.ticker, "data_group": row.data_group,
                          "revision": row.revision, "priority": row.priority,
                          "token": row.lease_token, "attempts": row.attempts,
                          "payload": dict(row.payload_json), "previous_result": dict(row.result_json)})
        db.commit()
        return items


def heartbeat(item: dict) -> bool:
    with SessionLocal() as db:
        row = db.get(RefreshWorkItem, item["key"], with_for_update=True)
        if row is None or row.lease_token != item["token"]:
            return False
        row.lease_until = datetime.now(UTC) + timedelta(minutes=5)
        db.commit()
        return True


def heartbeat_many(items: list[dict]) -> None:
    tokens = {item["key"]: item["token"] for item in items}
    with SessionLocal() as db:
        rows = db.scalars(select(RefreshWorkItem).where(RefreshWorkItem.key.in_(tokens))).all()
        deadline = datetime.now(UTC) + timedelta(minutes=5)
        for row in rows:
            if row.lease_token == tokens[row.key]:
                row.lease_until = deadline
        db.commit()


def finish(item: dict, *, result: dict, status: str, delay: timedelta, error: str = "") -> bool:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        row = db.get(RefreshWorkItem, item["key"], with_for_update=True)
        if row is None or row.lease_token != item["token"]:
            return False
        if row.revision != item["revision"]:
            row.status, row.due_at = "queued", now
        else:
            row.status, row.due_at = status, now + delay
            row.result_json = result
            row.error = error[:500]
            row.checked_at = now
        row.lease_token = row.lease_until = None
        db.commit()
        return True


def summary() -> dict:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        reason = case((RefreshWorkItem.status == "waiting_source",
                       func.coalesce(RefreshWorkItem.result_json["reason_code"].astext, "missing_history")),
                      else_="")
        counts = db.execute(select(
            RefreshWorkItem.data_group, RefreshWorkItem.status, reason, func.count(),
            func.count().filter(RefreshWorkItem.due_at <= now),
            func.min(RefreshWorkItem.due_at).filter(RefreshWorkItem.due_at > now),
        )
                            .group_by(RefreshWorkItem.data_group, RefreshWorkItem.status, reason)).all()
        due = db.scalar(select(func.count()).select_from(RefreshWorkItem).where(RefreshWorkItem.due_at <= now)) or 0
        oldest = db.scalar(select(func.min(RefreshWorkItem.due_at)).where(RefreshWorkItem.due_at <= now))
        next_due = db.scalar(select(func.min(RefreshWorkItem.due_at)).where(RefreshWorkItem.due_at > now))
        active = db.scalars(select(RefreshWorkItem).where(
            RefreshWorkItem.status == "running", RefreshWorkItem.lease_until > now,
        ).limit(5)).all()
        return {"due_count": due, "oldest_due_at": oldest, "next_due_at": next_due, "groups": [
            {"group": group, "status": status, "reason_code": reason_code,
             "count": count, "due_count": due_count,
             "next_due_at": next_check}
            for group, status, reason_code, count, due_count, next_check in counts
        ], "active": [{"ticker": row.ticker, "group": row.data_group, "lease_until": row.lease_until} for row in active]}
