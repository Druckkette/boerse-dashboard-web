"""Postgres owns pending work; broker messages only wake the worker."""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import case, func, or_, select, text
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


def wake_price_dependents(tickers: list[str]) -> dict[str, int]:
    """Retry waiting work only when newly available prices can satisfy its gate.

    The ordinary baseline planner deliberately preserves backoff. A price update
    is new evidence, so it may bring the next check forward without resetting
    attempts or discarding the previous diagnostic result.
    """
    clean = sorted({ticker.strip().upper() for ticker in tickers if ticker.strip()})
    if not clean:
        return {"beta": 0, "assessment": 0}
    # Updating SPY can complete an otherwise unchanged stock/SPY overlap.
    include_all_beta = "SPY" in clean
    statement = text("""
        WITH candidates AS (
            SELECT w.key, w.data_group, w.checked_at, i.id AS instrument_id
            FROM refresh_work_items w
            JOIN instruments i ON i.ticker = w.ticker
            WHERE w.status = 'waiting_source'
              AND w.data_group IN ('beta', 'assessment')
              AND w.due_at > now()
              AND (w.ticker = ANY(:tickers) OR (:all_beta AND w.data_group = 'beta'))
        ), eligible AS (
            SELECT c.key, c.data_group
            FROM candidates c
            JOIN LATERAL (
                SELECT count(DISTINCT p.date) AS days,
                       max(p.date) AS newest,
                       count(DISTINCT p.date) FILTER (WHERE spy.date IS NOT NULL) AS common_days,
                       max(p.date) FILTER (WHERE spy.date IS NOT NULL) AS newest_common
                FROM price_bars p
                LEFT JOIN price_bars spy
                  ON spy.date = p.date
                 AND spy.instrument_id = (SELECT id FROM instruments WHERE ticker = 'SPY' LIMIT 1)
                 AND spy.adj_close > 0
                WHERE p.instrument_id = c.instrument_id
                  AND p.date >= current_date - 400
                  AND p.adj_close > 0
            ) bars ON true
            WHERE (c.data_group = 'assessment'
                   AND bars.days >= 50 AND bars.newest > c.checked_at::date)
               OR (c.data_group = 'beta'
                   AND bars.common_days >= 91
                   AND bars.newest_common >= current_date - 14
                   AND (bars.newest > c.checked_at::date OR :all_beta))
        ), changed AS (
            UPDATE refresh_work_items w
            SET due_at = now(), status = 'queued'
            FROM eligible e
            WHERE w.key = e.key AND w.status = 'waiting_source'
            RETURNING w.data_group
        )
        SELECT data_group, count(*) FROM changed GROUP BY data_group
    """)
    with SessionLocal() as db:
        rows = db.execute(statement, {"tickers": clean, "all_beta": include_all_beta}).all()
        db.commit()
    counts = {"beta": 0, "assessment": 0}
    counts.update({group: count for group, count in rows})
    return counts


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
            func.count().filter(RefreshWorkItem.checked_at >= now - timedelta(hours=24)),
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
             "count": count, "due_count": due_count, "checked_24h": checked_24h,
             "next_due_at": next_check}
            for group, status, reason_code, count, due_count, next_check, checked_24h in counts
        ], "active": [{"ticker": row.ticker, "group": row.data_group, "lease_until": row.lease_until} for row in active]}
