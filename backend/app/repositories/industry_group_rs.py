from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import (
    IndustryGroup,
    IndustryGroupMembership,
    IndustryGroupRsSnapshot,
    Instrument,
    PriceBar,
)
from app.db.session import SessionLocal


class IndustryGroupRsRepositoryUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class GroupMemberRow:
    group_id: str
    group_code: str
    group_name: str
    sector: str
    industry_family: str
    instrument_id: str
    ticker: str
    name: str
    isin: str
    metadata_json: dict


@dataclass(frozen=True)
class PricePoint:
    date: date
    close: float
    volume: float | None


@dataclass(frozen=True)
class SnapshotWrite:
    industry_group_id: str
    snapshot_date: date
    taxonomy_version: str
    algorithm_version: str
    benchmark_ticker: str
    member_count: int
    eligible_member_count: int
    issuer_count: int
    return_1d: float | None
    return_1m: float | None
    return_3m: float | None
    return_6m: float | None
    return_12m: float | None
    benchmark_return_1d: float | None
    benchmark_return_1m: float | None
    benchmark_return_3m: float | None
    benchmark_return_6m: float | None
    benchmark_return_12m: float | None
    excess_return_1m: float | None
    excess_return_3m: float | None
    excess_return_6m: float | None
    excess_return_12m: float | None
    rs_1m: float | None
    rs_3m: float | None
    rs_6m: float | None
    rs_12m: float | None
    rs_score: float | None
    rank: int | None
    ranked_group_count: int
    is_ranked: bool
    member_metrics_json: list
    performance_series_json: list
    metadata_json: dict


def list_group_members(taxonomy_version: str) -> list[GroupMemberRow]:
    try:
        with SessionLocal() as db:
            rows = db.execute(
                select(IndustryGroup, IndustryGroupMembership, Instrument)
                .join(
                    IndustryGroupMembership,
                    IndustryGroupMembership.industry_group_id == IndustryGroup.id,
                )
                .join(Instrument, Instrument.id == IndustryGroupMembership.instrument_id)
                .where(
                    IndustryGroup.taxonomy_version == taxonomy_version,
                    IndustryGroup.active.is_(True),
                    IndustryGroupMembership.status == "classified",
                    IndustryGroupMembership.assignment_version == taxonomy_version,
                )
                .order_by(IndustryGroup.group_code.asc(), Instrument.ticker.asc())
            ).all()
            return [
                GroupMemberRow(
                    group_id=group.id,
                    group_code=group.group_code,
                    group_name=group.name,
                    sector=group.sector,
                    industry_family=group.industry_family,
                    instrument_id=instrument.id,
                    ticker=instrument.ticker,
                    name=instrument.name or instrument.ticker,
                    isin=instrument.isin or "",
                    metadata_json=instrument.metadata_json or {},
                )
                for group, membership, instrument in rows
            ]
    except SQLAlchemyError as exc:
        raise IndustryGroupRsRepositoryUnavailable(str(exc)) from exc


def list_price_history_for_tickers(
    tickers: Iterable[str],
    *,
    max_points: int = 540,
) -> dict[str, list[PricePoint]]:
    clean = list(dict.fromkeys(str(ticker).strip().upper() for ticker in tickers if str(ticker).strip()))
    if not clean:
        return {}
    try:
        with SessionLocal() as db:
            ranked = (
                select(
                    Instrument.ticker.label("ticker"),
                    PriceBar.date.label("date"),
                    func.coalesce(PriceBar.adj_close, PriceBar.close).label("close"),
                    PriceBar.volume.label("volume"),
                    func.row_number()
                    .over(
                        partition_by=Instrument.ticker,
                        order_by=PriceBar.date.desc(),
                    )
                    .label("rn"),
                )
                .join(PriceBar, PriceBar.instrument_id == Instrument.id)
                .where(
                    Instrument.ticker.in_(clean),
                    func.coalesce(PriceBar.adj_close, PriceBar.close).is_not(None),
                )
                .subquery()
            )
            rows = db.execute(
                select(ranked.c.ticker, ranked.c.date, ranked.c.close, ranked.c.volume)
                .where(ranked.c.rn <= max(2, int(max_points)))
                .order_by(ranked.c.ticker.asc(), ranked.c.date.asc())
            ).all()
            result: dict[str, list[PricePoint]] = {ticker: [] for ticker in clean}
            for ticker, point_date, close, volume in rows:
                if close is None:
                    continue
                result.setdefault(str(ticker).upper(), []).append(
                    PricePoint(
                        date=point_date,
                        close=float(close),
                        volume=float(volume) if volume is not None else None,
                    )
                )
            return result
    except SQLAlchemyError as exc:
        raise IndustryGroupRsRepositoryUnavailable(str(exc)) from exc


def upsert_snapshots(rows: list[SnapshotWrite]) -> int:
    if not rows:
        return 0
    calculated_at = datetime.now(UTC)
    try:
        with SessionLocal() as db:
            group_ids = list({row.industry_group_id for row in rows})
            dates = list({row.snapshot_date for row in rows})
            algorithms = list({row.algorithm_version for row in rows})
            existing = db.scalars(
                select(IndustryGroupRsSnapshot).where(
                    IndustryGroupRsSnapshot.industry_group_id.in_(group_ids),
                    IndustryGroupRsSnapshot.snapshot_date.in_(dates),
                    IndustryGroupRsSnapshot.algorithm_version.in_(algorithms),
                )
            ).all()
            by_key = {
                (row.industry_group_id, row.snapshot_date, row.algorithm_version): row
                for row in existing
            }
            for item in rows:
                key = (item.industry_group_id, item.snapshot_date, item.algorithm_version)
                target = by_key.get(key)
                if target is None:
                    target = IndustryGroupRsSnapshot(
                        industry_group_id=item.industry_group_id,
                        snapshot_date=item.snapshot_date,
                        algorithm_version=item.algorithm_version,
                    )
                    db.add(target)
                    by_key[key] = target
                target.taxonomy_version = item.taxonomy_version
                target.benchmark_ticker = item.benchmark_ticker
                target.member_count = item.member_count
                target.eligible_member_count = item.eligible_member_count
                target.issuer_count = item.issuer_count
                target.return_1d = item.return_1d
                target.return_1m = item.return_1m
                target.return_3m = item.return_3m
                target.return_6m = item.return_6m
                target.return_12m = item.return_12m
                target.benchmark_return_1d = item.benchmark_return_1d
                target.benchmark_return_1m = item.benchmark_return_1m
                target.benchmark_return_3m = item.benchmark_return_3m
                target.benchmark_return_6m = item.benchmark_return_6m
                target.benchmark_return_12m = item.benchmark_return_12m
                target.excess_return_1m = item.excess_return_1m
                target.excess_return_3m = item.excess_return_3m
                target.excess_return_6m = item.excess_return_6m
                target.excess_return_12m = item.excess_return_12m
                target.rs_1m = item.rs_1m
                target.rs_3m = item.rs_3m
                target.rs_6m = item.rs_6m
                target.rs_12m = item.rs_12m
                target.rs_score = item.rs_score
                target.rank = item.rank
                target.ranked_group_count = item.ranked_group_count
                target.is_ranked = item.is_ranked
                target.member_metrics_json = item.member_metrics_json
                target.performance_series_json = item.performance_series_json
                target.metadata_json = item.metadata_json
                target.calculated_at = calculated_at
            db.commit()
            return len(rows)
    except SQLAlchemyError as exc:
        raise IndustryGroupRsRepositoryUnavailable(str(exc)) from exc


def latest_snapshot_date(
    *,
    taxonomy_version: str,
    algorithm_version: str,
) -> date | None:
    try:
        with SessionLocal() as db:
            return db.scalar(
                select(func.max(IndustryGroupRsSnapshot.snapshot_date)).where(
                    IndustryGroupRsSnapshot.taxonomy_version == taxonomy_version,
                    IndustryGroupRsSnapshot.algorithm_version == algorithm_version,
                )
            )
    except SQLAlchemyError as exc:
        raise IndustryGroupRsRepositoryUnavailable(str(exc)) from exc


def snapshot_count(*, taxonomy_version: str, algorithm_version: str) -> int:
    try:
        with SessionLocal() as db:
            return int(
                db.scalar(
                    select(func.count())
                    .select_from(IndustryGroupRsSnapshot)
                    .where(
                        IndustryGroupRsSnapshot.taxonomy_version == taxonomy_version,
                        IndustryGroupRsSnapshot.algorithm_version == algorithm_version,
                    )
                )
                or 0
            )
    except SQLAlchemyError as exc:
        raise IndustryGroupRsRepositoryUnavailable(str(exc)) from exc


def list_latest_snapshots(
    *,
    taxonomy_version: str,
    algorithm_version: str,
) -> list[tuple[IndustryGroup, IndustryGroupRsSnapshot]]:
    latest = latest_snapshot_date(
        taxonomy_version=taxonomy_version,
        algorithm_version=algorithm_version,
    )
    if latest is None:
        return []
    try:
        with SessionLocal() as db:
            return list(
                db.execute(
                    select(IndustryGroup, IndustryGroupRsSnapshot)
                    .join(
                        IndustryGroupRsSnapshot,
                        IndustryGroupRsSnapshot.industry_group_id == IndustryGroup.id,
                    )
                    .where(
                        IndustryGroupRsSnapshot.snapshot_date == latest,
                        IndustryGroupRsSnapshot.taxonomy_version == taxonomy_version,
                        IndustryGroupRsSnapshot.algorithm_version == algorithm_version,
                        IndustryGroup.taxonomy_version == taxonomy_version,
                    )
                    .order_by(
                        IndustryGroupRsSnapshot.rank.asc().nulls_last(),
                        IndustryGroup.name.asc(),
                    )
                ).all()
            )
    except SQLAlchemyError as exc:
        raise IndustryGroupRsRepositoryUnavailable(str(exc)) from exc


def get_latest_group_snapshot(
    group_code: str,
    *,
    taxonomy_version: str,
    algorithm_version: str,
) -> tuple[IndustryGroup, IndustryGroupRsSnapshot] | None:
    clean = group_code.strip().upper()
    latest = latest_snapshot_date(
        taxonomy_version=taxonomy_version,
        algorithm_version=algorithm_version,
    )
    if latest is None:
        return None
    try:
        with SessionLocal() as db:
            return db.execute(
                select(IndustryGroup, IndustryGroupRsSnapshot)
                .join(
                    IndustryGroupRsSnapshot,
                    IndustryGroupRsSnapshot.industry_group_id == IndustryGroup.id,
                )
                .where(
                    IndustryGroup.group_code == clean,
                    IndustryGroup.taxonomy_version == taxonomy_version,
                    IndustryGroupRsSnapshot.snapshot_date == latest,
                    IndustryGroupRsSnapshot.algorithm_version == algorithm_version,
                )
                .limit(1)
            ).one_or_none()
    except SQLAlchemyError as exc:
        raise IndustryGroupRsRepositoryUnavailable(str(exc)) from exc


def get_group_for_ticker(
    ticker: str,
    *,
    taxonomy_version: str,
) -> tuple[IndustryGroup, IndustryGroupMembership, Instrument] | None:
    clean = ticker.strip().upper()
    try:
        with SessionLocal() as db:
            return db.execute(
                select(IndustryGroup, IndustryGroupMembership, Instrument)
                .join(
                    IndustryGroupMembership,
                    IndustryGroupMembership.industry_group_id == IndustryGroup.id,
                )
                .join(Instrument, Instrument.id == IndustryGroupMembership.instrument_id)
                .where(
                    Instrument.ticker == clean,
                    IndustryGroup.taxonomy_version == taxonomy_version,
                    IndustryGroupMembership.assignment_version == taxonomy_version,
                    IndustryGroupMembership.status == "classified",
                )
                .limit(1)
            ).one_or_none()
    except SQLAlchemyError as exc:
        raise IndustryGroupRsRepositoryUnavailable(str(exc)) from exc


def list_group_snapshot_history(
    group_id: str,
    *,
    algorithm_version: str,
    limit: int = 30,
) -> list[IndustryGroupRsSnapshot]:
    try:
        with SessionLocal() as db:
            rows = db.scalars(
                select(IndustryGroupRsSnapshot)
                .where(
                    IndustryGroupRsSnapshot.industry_group_id == group_id,
                    IndustryGroupRsSnapshot.algorithm_version == algorithm_version,
                )
                .order_by(IndustryGroupRsSnapshot.snapshot_date.desc())
                .limit(max(1, min(300, int(limit))))
            ).all()
            return list(rows)
    except SQLAlchemyError as exc:
        raise IndustryGroupRsRepositoryUnavailable(str(exc)) from exc


def list_group_snapshot_histories(
    group_ids: Iterable[str],
    *,
    algorithm_version: str,
    limit: int = 30,
) -> dict[str, list[IndustryGroupRsSnapshot]]:
    clean = list(dict.fromkeys(str(group_id) for group_id in group_ids if str(group_id)))
    if not clean:
        return {}
    capped_limit = max(1, min(300, int(limit)))
    try:
        with SessionLocal() as db:
            ranked = (
                select(
                    IndustryGroupRsSnapshot.id.label("snapshot_id"),
                    IndustryGroupRsSnapshot.industry_group_id.label("industry_group_id"),
                    func.row_number()
                    .over(
                        partition_by=IndustryGroupRsSnapshot.industry_group_id,
                        order_by=IndustryGroupRsSnapshot.snapshot_date.desc(),
                    )
                    .label("rn"),
                )
                .where(
                    IndustryGroupRsSnapshot.industry_group_id.in_(clean),
                    IndustryGroupRsSnapshot.algorithm_version == algorithm_version,
                )
                .subquery()
            )
            rows = db.scalars(
                select(IndustryGroupRsSnapshot)
                .join(ranked, ranked.c.snapshot_id == IndustryGroupRsSnapshot.id)
                .where(ranked.c.rn <= capped_limit)
                .order_by(
                    IndustryGroupRsSnapshot.industry_group_id.asc(),
                    IndustryGroupRsSnapshot.snapshot_date.desc(),
                )
            ).all()
            result: dict[str, list[IndustryGroupRsSnapshot]] = {
                group_id: [] for group_id in clean
            }
            for row in rows:
                result.setdefault(row.industry_group_id, []).append(row)
            return result
    except SQLAlchemyError as exc:
        raise IndustryGroupRsRepositoryUnavailable(str(exc)) from exc
