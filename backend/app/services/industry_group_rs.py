from __future__ import annotations

import re
from bisect import bisect_right
from collections import defaultdict
from dataclasses import replace
from datetime import date
from statistics import fmean
from time import monotonic

from app.domain.stocks.industry_groups import TAXONOMY_VERSION
from app.repositories import industry_group_rs as repository
from app.repositories import stock_assessments as stock_assessment_repository


ALGORITHM_VERSION = "industry_group_rs_v3"
DEFAULT_BENCHMARK = "SPY"
MIN_GROUP_MEMBERS_FOR_RS = 5
WINSOR_LOWER_QUANTILE = 0.05
WINSOR_UPPER_QUANTILE = 0.95
INDUSTRY_GROUP_RS_WEIGHTS = {
    "1m": 0.15,
    "3m": 0.25,
    "6m": 0.30,
    "12m": 0.30,
}
HORIZON_SESSIONS = {
    "1d": 1,
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "12m": 252,
}
MEMBER_1W_SESSIONS = 5


def _issuer_key(member: repository.GroupMemberRow) -> str:
    metadata = member.metadata_json or {}
    issuer_id = str(
        metadata.get("issuer_id")
        or metadata.get("company_identifier")
        or metadata.get("company_id")
        or ""
    ).strip()
    if issuer_id:
        return f"issuer:{issuer_id}"
    cik = str(metadata.get("primary_cik") or metadata.get("cik") or "").strip().lstrip("0")
    if cik:
        return f"cik:{cik}"
    name = member.name.lower()
    name = re.sub(r"\b(class|series)\s+[a-z0-9]+\b", " ", name)
    name = re.sub(r"\b(common stock|ordinary shares?|common shares?|ads|adr)\b", " ", name)
    name = re.sub(r"[^a-z0-9]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    if name:
        return f"name:{name}"
    if member.isin:
        return f"isin:{member.isin}"
    return f"instrument:{member.instrument_id}"


def _point_index(points: list[repository.PricePoint], as_of: date) -> int:
    if not points:
        return -1
    dates = [point.date for point in points]
    return bisect_right(dates, as_of) - 1


def _current_point_index(points: list[repository.PricePoint], as_of: date) -> int:
    index = _point_index(points, as_of)
    if index < 0 or points[index].date != as_of:
        return -1
    return index


def _return_pct(
    points: list[repository.PricePoint],
    as_of: date,
    sessions: int,
) -> float | None:
    index = _current_point_index(points, as_of)
    if index < sessions:
        return None
    current = points[index].close
    previous = points[index - sessions].close
    if current <= 0 or previous <= 0:
        return None
    return (current / previous - 1.0) * 100.0


def _return_pct_between_dates(
    points: list[repository.PricePoint],
    start_date: date | None,
    end_date: date,
) -> float | None:
    if start_date is None:
        return None
    start_index = _current_point_index(points, start_date)
    end_index = _current_point_index(points, end_date)
    if start_index < 0 or end_index < 0 or start_index >= end_index:
        return None
    current = points[end_index].close
    previous = points[start_index].close
    if current <= 0 or previous <= 0:
        return None
    return (current / previous - 1.0) * 100.0


def _benchmark_session_starts(
    benchmark_points: list[repository.PricePoint],
    as_of: date,
    sessions: set[int],
) -> dict[int, date | None]:
    index = _current_point_index(benchmark_points, as_of)
    return {
        session_count: (
            benchmark_points[index - session_count].date
            if index >= session_count
            else None
        )
        for session_count in sessions
    }


def _latest_close(points: list[repository.PricePoint], as_of: date) -> float | None:
    index = _current_point_index(points, as_of)
    return points[index].close if index >= 0 else None


def _average_dollar_volume(
    points: list[repository.PricePoint],
    as_of: date,
    sessions: int = 20,
) -> float:
    index = _current_point_index(points, as_of)
    if index < 0:
        return 0.0
    values = [
        point.close * point.volume
        for point in points[max(0, index - sessions + 1) : index + 1]
        if point.volume is not None and point.volume > 0 and point.close > 0
    ]
    return fmean(values) if values else 0.0


def _quantile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile requires at least one value")
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, quantile)) * (len(ordered) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def _winsorized_mean(
    values: list[float],
    *,
    lower_quantile: float = WINSOR_LOWER_QUANTILE,
    upper_quantile: float = WINSOR_UPPER_QUANTILE,
) -> float | None:
    if not values:
        return None
    if len(values) < 3:
        return fmean(values)
    lower = _quantile(values, lower_quantile)
    upper = _quantile(values, upper_quantile)
    clipped = [min(upper, max(lower, value)) for value in values]
    return fmean(clipped)


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda item: (item[1], item[0]))
    count = len(ordered)
    if count == 1:
        return {ordered[0][0]: 100.0}

    result: dict[str, float] = {}
    start = 0
    while start < count:
        end = start
        value = ordered[start][1]
        while end + 1 < count and ordered[end + 1][1] == value:
            end += 1
        average_index = (start + end) / 2.0
        percentile = round(1.0 + 99.0 * average_index / (count - 1), 2)
        for index in range(start, end + 1):
            result[ordered[index][0]] = percentile
        start = end + 1
    return result


def _representatives(
    members: list[repository.GroupMemberRow],
    price_history: dict[str, list[repository.PricePoint]],
    as_of: date,
) -> tuple[list[repository.GroupMemberRow], dict[str, str]]:
    by_issuer: dict[str, list[repository.GroupMemberRow]] = defaultdict(list)
    for member in members:
        by_issuer[_issuer_key(member)].append(member)
    representatives: list[repository.GroupMemberRow] = []
    representative_by_ticker: dict[str, str] = {}
    for issuer, rows in by_issuer.items():
        selected = max(
            rows,
            key=lambda row: (
                _average_dollar_volume(price_history.get(row.ticker, []), as_of),
                len(price_history.get(row.ticker, [])),
                row.ticker,
            ),
        )
        representatives.append(selected)
        for row in rows:
            representative_by_ticker[row.ticker] = selected.ticker
    return representatives, representative_by_ticker


def _performance_series(
    representatives: list[repository.GroupMemberRow],
    price_history: dict[str, list[repository.PricePoint]],
    benchmark_points: list[repository.PricePoint],
    as_of: date,
    *,
    lookback_sessions: int = 252,
) -> list[dict]:
    benchmark_dates = [point.date for point in benchmark_points if point.date <= as_of][-(lookback_sessions + 1):]
    if len(benchmark_dates) < 2:
        return []
    ticker_maps = {
        row.ticker: {point.date: point.close for point in price_history.get(row.ticker, [])}
        for row in representatives
    }
    benchmark_map = {point.date: point.close for point in benchmark_points}
    group_index = 100.0
    benchmark_index = 100.0
    series = [
        {
            "date": benchmark_dates[0].isoformat(),
            "group_index": 100.0,
            "benchmark_index": 100.0,
            "eligible_members": 0,
        }
    ]
    for previous_date, current_date in zip(benchmark_dates, benchmark_dates[1:]):
        daily_returns = []
        for row in representatives:
            values = ticker_maps.get(row.ticker, {})
            previous = values.get(previous_date)
            current = values.get(current_date)
            if previous and current and previous > 0 and current > 0:
                daily_returns.append(current / previous - 1.0)
        robust_daily_return = _winsorized_mean(daily_returns)
        if robust_daily_return is not None:
            group_index *= 1.0 + robust_daily_return
        previous_benchmark = benchmark_map.get(previous_date)
        current_benchmark = benchmark_map.get(current_date)
        if previous_benchmark and current_benchmark and previous_benchmark > 0 and current_benchmark > 0:
            benchmark_index *= current_benchmark / previous_benchmark
        series.append(
            {
                "date": current_date.isoformat(),
                "group_index": round(group_index, 8),
                "benchmark_index": round(benchmark_index, 8),
                "eligible_members": len(daily_returns),
            }
        )
    return series


def _series_return_pct(
    series: list[dict],
    as_of: date,
    sessions: int,
) -> float | None:
    if not series:
        return None
    dates = [date.fromisoformat(str(point["date"])) for point in series]
    index = bisect_right(dates, as_of) - 1
    if index < sessions or dates[index] != as_of:
        return None
    window = series[index - sessions + 1 : index + 1]
    if any(
        "eligible_members" in point and int(point.get("eligible_members") or 0) <= 0
        for point in window
    ):
        return None
    current = float(series[index]["group_index"])
    previous = float(series[index - sessions]["group_index"])
    if current <= 0 or previous <= 0:
        return None
    return (current / previous - 1.0) * 100.0


def _minimum_daily_eligible_members(
    series: list[dict],
    as_of: date,
    sessions: int,
) -> int | None:
    if not series:
        return None
    dates = [date.fromisoformat(str(point["date"])) for point in series]
    index = bisect_right(dates, as_of) - 1
    if index < sessions or dates[index] != as_of:
        return None
    window = series[index - sessions + 1 : index + 1]
    return min(int(point.get("eligible_members") or 0) for point in window)


def _member_metrics(
    members: list[repository.GroupMemberRow],
    representatives: list[repository.GroupMemberRow],
    representative_by_ticker: dict[str, str],
    price_history: dict[str, list[repository.PricePoint]],
    as_of: date,
    *,
    benchmark_session_starts: dict[int, date | None] | None = None,
) -> list[dict]:
    representative_tickers = {row.ticker for row in representatives}
    result = []
    session_starts = benchmark_session_starts or {}

    def member_return(points: list[repository.PricePoint], sessions: int) -> float | None:
        if benchmark_session_starts is None:
            return _return_pct(points, as_of, sessions)
        return _return_pct_between_dates(points, session_starts.get(sessions), as_of)

    for member in members:
        points = price_history.get(member.ticker, [])
        result.append(
            {
                "ticker": member.ticker,
                "name": member.name,
                "issuer_key": _issuer_key(member),
                "issuer_representative": member.ticker in representative_tickers,
                "representative_ticker": representative_by_ticker.get(member.ticker, member.ticker),
                "latest_close": _latest_close(points, as_of),
                "average_dollar_volume_20d": round(_average_dollar_volume(points, as_of), 2),
                "return_1d": member_return(points, HORIZON_SESSIONS["1d"]),
                "return_1w": member_return(points, MEMBER_1W_SESSIONS),
                "return_1m": member_return(points, HORIZON_SESSIONS["1m"]),
                "return_3m": member_return(points, HORIZON_SESSIONS["3m"]),
                "return_6m": member_return(points, HORIZON_SESSIONS["6m"]),
                "return_12m": member_return(points, HORIZON_SESSIONS["12m"]),
            }
        )
    return result


def _raw_group_data(
    groups: dict[str, list[repository.GroupMemberRow]],
    price_history: dict[str, list[repository.PricePoint]],
    benchmark_points: list[repository.PricePoint],
    as_of: date,
    *,
    include_performance_series: bool,
    representatives_by_group: dict[str, tuple[list[repository.GroupMemberRow], dict[str, str]]] | None = None,
    performance_series_by_group: dict[str, list[dict]] | None = None,
) -> dict[str, dict]:
    benchmark_session_starts = _benchmark_session_starts(
        benchmark_points,
        as_of,
        set(HORIZON_SESSIONS.values()) | {MEMBER_1W_SESSIONS},
    )
    benchmark_returns = {
        horizon: _return_pct(benchmark_points, as_of, sessions)
        for horizon, sessions in HORIZON_SESSIONS.items()
    }
    raw: dict[str, dict] = {}
    for group_id, members in groups.items():
        if representatives_by_group and group_id in representatives_by_group:
            representatives, representative_by_ticker = representatives_by_group[group_id]
        else:
            representatives, representative_by_ticker = _representatives(
                members,
                price_history,
                as_of,
            )
        horizon_values: dict[str, list[float]] = {key: [] for key in HORIZON_SESSIONS}
        for member in representatives:
            points = price_history.get(member.ticker, [])
            for horizon, sessions in HORIZON_SESSIONS.items():
                value = _return_pct_between_dates(
                    points,
                    benchmark_session_starts.get(sessions),
                    as_of,
                )
                if value is not None:
                    horizon_values[horizon].append(value)

        if performance_series_by_group and group_id in performance_series_by_group:
            canonical_series = performance_series_by_group[group_id]
        else:
            canonical_series = _performance_series(
                representatives,
                price_history,
                benchmark_points,
                as_of,
            )
        returns = {
            horizon: _series_return_pct(canonical_series, as_of, sessions)
            for horizon, sessions in HORIZON_SESSIONS.items()
        }
        minimum_daily_eligible_counts = {
            horizon: _minimum_daily_eligible_members(canonical_series, as_of, sessions)
            for horizon, sessions in HORIZON_SESSIONS.items()
        }
        raw[group_id] = {
            "group": members[0],
            "member_count": len(members),
            "issuer_count": len(representatives),
            "eligible_member_count": len(horizon_values["1m"]),
            "eligible_counts": {key: len(value) for key, value in horizon_values.items()},
            "minimum_daily_eligible_counts": minimum_daily_eligible_counts,
            "returns": returns,
            "benchmark_returns": benchmark_returns,
            "member_metrics": _member_metrics(
                members,
                representatives,
                representative_by_ticker,
                price_history,
                as_of,
                benchmark_session_starts=benchmark_session_starts,
            ),
            "performance_series": (
                [
                    point
                    for point in canonical_series
                    if date.fromisoformat(str(point["date"])) <= as_of
                ][-253:]
                if include_performance_series
                else []
            ),
        }
    return raw


def _rank_raw(raw: dict[str, dict]) -> None:
    horizon_percentiles: dict[str, dict[str, float]] = {}
    for horizon in ("1m", "3m", "6m", "12m"):
        candidates = {
            group_id: item["returns"][horizon]
            for group_id, item in raw.items()
            if item["issuer_count"] >= MIN_GROUP_MEMBERS_FOR_RS
            and item["eligible_counts"][horizon] >= MIN_GROUP_MEMBERS_FOR_RS
            and (item["minimum_daily_eligible_counts"][horizon] or 0)
            >= MIN_GROUP_MEMBERS_FOR_RS
            and item["returns"][horizon] is not None
        }
        horizon_percentiles[horizon] = _percentiles(candidates)

    composite: dict[str, float] = {}
    for group_id, item in raw.items():
        rs_values = {
            horizon: horizon_percentiles[horizon].get(group_id)
            for horizon in ("1m", "3m", "6m", "12m")
        }
        item["rs"] = rs_values
        if all(value is not None for value in rs_values.values()):
            score = sum(
                float(rs_values[horizon]) * INDUSTRY_GROUP_RS_WEIGHTS[horizon]
                for horizon in INDUSTRY_GROUP_RS_WEIGHTS
            )
            item["rs_score"] = round(score, 2)
            composite[group_id] = score
        else:
            item["rs_score"] = None

    ordered = sorted(composite.items(), key=lambda item: (-item[1], item[0]))
    ranked_count = len(ordered)
    ranks: dict[str, int] = {}
    previous_score: float | None = None
    current_rank = 0
    for index, (group_id, score) in enumerate(ordered, start=1):
        if previous_score is None or score != previous_score:
            current_rank = index
            previous_score = score
        ranks[group_id] = current_rank
    for group_id, item in raw.items():
        item["rank"] = ranks.get(group_id)
        item["ranked_group_count"] = ranked_count
        item["is_ranked"] = group_id in ranks


def _snapshot_writes(
    raw: dict[str, dict],
    as_of: date,
    *,
    benchmark_ticker: str,
) -> list[repository.SnapshotWrite]:
    result = []
    for group_id, item in raw.items():
        group = item["group"]
        returns = item["returns"]
        benchmark = item["benchmark_returns"]
        result.append(
            repository.SnapshotWrite(
                industry_group_id=group_id,
                snapshot_date=as_of,
                taxonomy_version=TAXONOMY_VERSION,
                algorithm_version=ALGORITHM_VERSION,
                benchmark_ticker=benchmark_ticker,
                member_count=item["member_count"],
                eligible_member_count=item["eligible_member_count"],
                issuer_count=item["issuer_count"],
                return_1d=returns["1d"],
                return_1m=returns["1m"],
                return_3m=returns["3m"],
                return_6m=returns["6m"],
                return_12m=returns["12m"],
                benchmark_return_1d=benchmark["1d"],
                benchmark_return_1m=benchmark["1m"],
                benchmark_return_3m=benchmark["3m"],
                benchmark_return_6m=benchmark["6m"],
                benchmark_return_12m=benchmark["12m"],
                excess_return_1m=(returns["1m"] - benchmark["1m"] if returns["1m"] is not None and benchmark["1m"] is not None else None),
                excess_return_3m=(returns["3m"] - benchmark["3m"] if returns["3m"] is not None and benchmark["3m"] is not None else None),
                excess_return_6m=(returns["6m"] - benchmark["6m"] if returns["6m"] is not None and benchmark["6m"] is not None else None),
                excess_return_12m=(returns["12m"] - benchmark["12m"] if returns["12m"] is not None and benchmark["12m"] is not None else None),
                rs_1m=item["rs"].get("1m"),
                rs_3m=item["rs"].get("3m"),
                rs_6m=item["rs"].get("6m"),
                rs_12m=item["rs"].get("12m"),
                rs_score=item["rs_score"],
                rank=item["rank"],
                ranked_group_count=item["ranked_group_count"],
                is_ranked=item["is_ranked"],
                member_metrics_json=item["member_metrics"],
                performance_series_json=item["performance_series"],
                metadata_json={
                    "weights": INDUSTRY_GROUP_RS_WEIGHTS,
                    "horizon_sessions": HORIZON_SESSIONS,
                    "eligible_counts": item["eligible_counts"],
                    "minimum_daily_eligible_counts": item["minimum_daily_eligible_counts"],
                    "min_group_members_for_rs": MIN_GROUP_MEMBERS_FOR_RS,
                    "aggregation": "daily_equal_weight_winsorized_5_95",
                    "winsor_lower_quantile": WINSOR_LOWER_QUANTILE,
                    "winsor_upper_quantile": WINSOR_UPPER_QUANTILE,
                    "group_code": group.group_code,
                },
            )
        )
    return result


def refresh_industry_group_rs(
    *,
    benchmark_ticker: str = DEFAULT_BENCHMARK,
    backfill_sessions: int | None = None,
) -> dict:
    started = monotonic()
    benchmark = benchmark_ticker.strip().upper() or DEFAULT_BENCHMARK
    members = repository.list_group_members(TAXONOMY_VERSION)
    groups: dict[str, list[repository.GroupMemberRow]] = defaultdict(list)
    for member in members:
        groups[member.group_id].append(member)
    tickers = [member.ticker for member in members]
    if benchmark not in tickers:
        tickers.append(benchmark)

    if backfill_sessions is None:
        backfill_sessions = (
            20
            if repository.snapshot_count(
                taxonomy_version=TAXONOMY_VERSION,
                algorithm_version=ALGORITHM_VERSION,
            )
            == 0
            else 0
        )
    requested_backfill_sessions = max(0, min(252, int(backfill_sessions)))
    max_points = 253 + requested_backfill_sessions + 10
    price_history = repository.list_price_history_for_tickers(
        tickers,
        max_points=max_points,
    )
    benchmark_points = price_history.get(benchmark, [])
    if len(benchmark_points) < 253:
        raise RuntimeError(
            f"Benchmark {benchmark} hat nur {len(benchmark_points)} gespeicherte Kurszeilen; mindestens 253 erforderlich."
        )

    available_backfill_sessions = max(0, len(benchmark_points) - 253)
    backfill_sessions = min(requested_backfill_sessions, available_backfill_sessions)
    target_dates = [point.date for point in benchmark_points]
    target_dates = target_dates[-(backfill_sessions + 1) :]
    latest_date = target_dates[-1]

    representatives_by_group: dict[
        str,
        tuple[list[repository.GroupMemberRow], dict[str, str]],
    ] = {
        group_id: _representatives(group_members, price_history, latest_date)
        for group_id, group_members in groups.items()
    }
    performance_series_by_group = {
        group_id: _performance_series(
            representatives,
            price_history,
            benchmark_points,
            latest_date,
            lookback_sessions=252 + backfill_sessions,
        )
        for group_id, (representatives, _mapping) in representatives_by_group.items()
    }

    all_writes: list[repository.SnapshotWrite] = []
    latest_raw: dict[str, dict] = {}
    for target_date in target_dates:
        raw = _raw_group_data(
            groups,
            price_history,
            benchmark_points,
            target_date,
            include_performance_series=target_date == latest_date,
            representatives_by_group=representatives_by_group,
            performance_series_by_group=performance_series_by_group,
        )
        _rank_raw(raw)
        all_writes.extend(
            _snapshot_writes(raw, target_date, benchmark_ticker=benchmark)
        )
        if target_date == latest_date:
            latest_raw = raw

    calculation_duration_seconds = round(monotonic() - started, 2)
    all_writes = [
        replace(
            item,
            metadata_json={
                **item.metadata_json,
                "calculation_duration_seconds": calculation_duration_seconds,
            },
        )
        if item.snapshot_date == latest_date
        else item
        for item in all_writes
    ]
    repository.upsert_snapshots(all_writes)
    ranked_groups = sum(1 for item in latest_raw.values() if item["is_ranked"])
    small_groups = sum(
        1 for item in latest_raw.values() if item["issuer_count"] < MIN_GROUP_MEMBERS_FOR_RS
    )
    insufficient_history_groups = sum(
        1
        for item in latest_raw.values()
        if item["issuer_count"] >= MIN_GROUP_MEMBERS_FOR_RS and not item["is_ranked"]
    )
    missing_price_histories = sum(
        1 for member in members if len(price_history.get(member.ticker, [])) < 22
    )
    return {
        "ok": True,
        "taxonomy_version": TAXONOMY_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "snapshot_date": latest_date.isoformat(),
        "benchmark": benchmark,
        "groups_processed": len(groups),
        "groups_ranked": ranked_groups,
        "small_groups": small_groups,
        "insufficient_history_groups": insufficient_history_groups,
        "stocks_processed": len(members),
        "issuers_processed": sum(item["issuer_count"] for item in latest_raw.values()),
        "missing_price_histories": missing_price_histories,
        "snapshots_written": len(all_writes),
        "requested_backfill_sessions": requested_backfill_sessions,
        "backfill_sessions": backfill_sessions,
        "backfill_complete": backfill_sessions == requested_backfill_sessions,
        "duration_seconds": round(monotonic() - started, 2),
        "weights": INDUSTRY_GROUP_RS_WEIGHTS,
        "min_group_members_for_rs": MIN_GROUP_MEMBERS_FOR_RS,
    }


def _snapshot_payload(group, snapshot) -> dict:
    rank_status = (
        "ranked"
        if snapshot.is_ranked
        else (
            "small_group"
            if int(snapshot.issuer_count) < MIN_GROUP_MEMBERS_FOR_RS
            else "insufficient_history"
        )
    )
    return {
        "id": group.id,
        "code": group.group_code,
        "name": group.name,
        "sector": group.sector,
        "industry_family": group.industry_family,
        "snapshot_date": snapshot.snapshot_date.isoformat(),
        "member_count": snapshot.member_count,
        "eligible_member_count": snapshot.eligible_member_count,
        "issuer_count": snapshot.issuer_count,
        "is_ranked": snapshot.is_ranked,
        "rank_status": rank_status,
        "rank": snapshot.rank,
        "ranked_group_count": snapshot.ranked_group_count,
        "rs_score": snapshot.rs_score,
        "rs_1m": snapshot.rs_1m,
        "rs_3m": snapshot.rs_3m,
        "rs_6m": snapshot.rs_6m,
        "rs_12m": snapshot.rs_12m,
        "return_1d": snapshot.return_1d,
        "return_1m": snapshot.return_1m,
        "return_3m": snapshot.return_3m,
        "return_6m": snapshot.return_6m,
        "return_12m": snapshot.return_12m,
        "benchmark_return_1m": snapshot.benchmark_return_1m,
        "benchmark_return_3m": snapshot.benchmark_return_3m,
        "benchmark_return_6m": snapshot.benchmark_return_6m,
        "benchmark_return_12m": snapshot.benchmark_return_12m,
        "excess_return_1m": snapshot.excess_return_1m,
        "excess_return_3m": snapshot.excess_return_3m,
        "excess_return_6m": snapshot.excess_return_6m,
        "excess_return_12m": snapshot.excess_return_12m,
        "benchmark_ticker": snapshot.benchmark_ticker,
        "algorithm_version": snapshot.algorithm_version,
        "taxonomy_version": snapshot.taxonomy_version,
    }


def _assessment_context(tickers: list[str]):
    clean = list(dict.fromkeys(ticker for ticker in tickers if ticker))
    assessments = stock_assessment_repository.list_all_snapshots(clean)
    return (
        {row.ticker.upper(): row for row in assessments},
        {row.ticker.upper(): index for index, row in enumerate(assessments)},
    )


def _ranked_members(
    snapshot,
    *,
    assessment_by_ticker=None,
    canonical_order: dict[str, int] | None = None,
) -> list[dict]:
    metrics = list(snapshot.member_metrics_json or [])
    tickers = [str(item.get("ticker") or "").upper() for item in metrics]
    if assessment_by_ticker is None or canonical_order is None:
        assessment_by_ticker, canonical_order = _assessment_context(tickers)
    by_ticker = assessment_by_ticker
    rows = []
    for metric in metrics:
        ticker = str(metric.get("ticker") or "").upper()
        assessment = by_ticker.get(ticker)
        item_json = assessment.item_json if assessment else {}
        rows.append(
            {
                **metric,
                "ticker": ticker,
                "overall_score": assessment.overall_score if assessment else None,
                "technical_score": assessment.technical_score if assessment else None,
                "stock_rs": item_json.get("rs_rating") if assessment else None,
                "fundamental_score": item_json.get("fundamental_score") if assessment else None,
                "moving_average_score": item_json.get("moving_average_score") if assessment else None,
                "chart_behavior_score": item_json.get("chart_behavior_score") if assessment else None,
                "verdict_label": item_json.get("verdict_label") if assessment else None,
            }
        )
    rows.sort(
        key=lambda item: (
            canonical_order.get(item["ticker"], len(canonical_order)),
            item["ticker"],
        )
    )
    for index, row in enumerate(rows, start=1):
        row["group_rank"] = index
        row["group_members"] = len(rows)
    return rows


def _top_members(members: list[dict], *, limit: int = 3) -> list[dict]:
    qualified = [
        item
        for item in members
        if item.get("latest_close") is not None and item.get("overall_score") is not None
    ]
    return qualified[:limit]


def _momentum_from_history(history) -> dict:
    if not history:
        return {
            "rank_5d_ago": None,
            "rank_20d_ago": None,
            "rank_change_5d": None,
            "rank_change_20d": None,
            "rs_5d_ago": None,
            "rs_20d_ago": None,
            "rs_change_5d": None,
            "rs_change_20d": None,
        }
    current = history[0]
    five = history[5] if len(history) > 5 else None
    twenty = history[20] if len(history) > 20 else None

    def rank_change(previous):
        if previous is None or current.rank is None or previous.rank is None:
            return None
        return previous.rank - current.rank

    def rs_change(previous):
        if previous is None or current.rs_score is None or previous.rs_score is None:
            return None
        return round(current.rs_score - previous.rs_score, 2)

    return {
        "rank_5d_ago": five.rank if five else None,
        "rank_20d_ago": twenty.rank if twenty else None,
        "rank_change_5d": rank_change(five),
        "rank_change_20d": rank_change(twenty),
        "rs_5d_ago": five.rs_score if five else None,
        "rs_20d_ago": twenty.rs_score if twenty else None,
        "rs_change_5d": rs_change(five),
        "rs_change_20d": rs_change(twenty),
    }


def _momentum(group_id: str) -> dict:
    return _momentum_from_history(
        repository.list_group_snapshot_history(
            group_id,
            algorithm_version=ALGORITHM_VERSION,
            limit=25,
        )
    )


def list_rankings(
    *,
    sector: str = "",
    industry_family: str = "",
    include_small: bool = True,
) -> dict:
    pairs = repository.list_latest_snapshots(
        taxonomy_version=TAXONOMY_VERSION,
        algorithm_version=ALGORITHM_VERSION,
    )
    all_tickers = [
        str(item.get("ticker") or "").upper()
        for _group, snapshot in pairs
        for item in list(snapshot.member_metrics_json or [])
        if str(item.get("ticker") or "").strip()
    ]
    assessment_by_ticker, canonical_order = _assessment_context(all_tickers)
    histories = repository.list_group_snapshot_histories(
        [group.id for group, _snapshot in pairs],
        algorithm_version=ALGORITHM_VERSION,
        limit=25,
    )
    rows = []
    for group, snapshot in pairs:
        if sector and group.sector != sector:
            continue
        if industry_family and group.industry_family != industry_family:
            continue
        if not include_small and not snapshot.is_ranked:
            continue
        ranked_members = _ranked_members(
            snapshot,
            assessment_by_ticker=assessment_by_ticker,
            canonical_order=canonical_order,
        )
        rows.append(
            {
                **_snapshot_payload(group, snapshot),
                **_momentum_from_history(histories.get(group.id, [])),
                "top_stock": (_top_members(ranked_members, limit=1) or [None])[0],
            }
        )
    return {
        "as_of": pairs[0][1].snapshot_date.isoformat() if pairs else date.today().isoformat(),
        "taxonomy_version": TAXONOMY_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "benchmark": pairs[0][1].benchmark_ticker if pairs else DEFAULT_BENCHMARK,
        "min_group_members_for_rs": MIN_GROUP_MEMBERS_FOR_RS,
        "weights": INDUSTRY_GROUP_RS_WEIGHTS,
        "rows": rows,
    }


def group_detail(group_code: str) -> dict | None:
    pair = repository.get_latest_group_snapshot(
        group_code,
        taxonomy_version=TAXONOMY_VERSION,
        algorithm_version=ALGORITHM_VERSION,
    )
    if pair is None:
        return None
    group, snapshot = pair
    members = _ranked_members(snapshot)
    return {
        "group": {
            **_snapshot_payload(group, snapshot),
            **_momentum(group.id),
        },
        "top_stocks": _top_members(members),
        "members": members,
        "performance_series": list(snapshot.performance_series_json or []),
    }


def stock_group_context(ticker: str) -> dict | None:
    membership = repository.get_group_for_ticker(
        ticker,
        taxonomy_version=TAXONOMY_VERSION,
    )
    if membership is None:
        return None
    group, _membership, _instrument = membership
    pair = repository.get_latest_group_snapshot(
        group.group_code,
        taxonomy_version=TAXONOMY_VERSION,
        algorithm_version=ALGORITHM_VERSION,
    )
    if pair is None:
        return {
            "group": {
                "id": group.id,
                "code": group.group_code,
                "name": group.name,
                "sector": group.sector,
                "industry_family": group.industry_family,
            },
            "stock": {"ticker": ticker.strip().upper(), "group_rank": None, "group_members": None},
            "top_stocks": [],
        }
    _group, snapshot = pair
    members = _ranked_members(snapshot)
    clean = ticker.strip().upper()
    stock = next((item for item in members if item["ticker"] == clean), None)
    return {
        "group": {
            **_snapshot_payload(group, snapshot),
            **_momentum(group.id),
        },
        "stock": stock or {"ticker": clean, "group_rank": None, "group_members": len(members)},
        "top_stocks": _top_members(members),
    }


def diagnostics() -> dict:
    ranking = list_rankings()
    rows = ranking["rows"]
    ranked = [row for row in rows if row["is_ranked"]]
    pairs = repository.list_latest_snapshots(
        taxonomy_version=TAXONOMY_VERSION,
        algorithm_version=ALGORITHM_VERSION,
    )
    missing_by_horizon = {
        horizon: sum(
            max(
                0,
                int(snapshot.issuer_count)
                - int(((snapshot.metadata_json or {}).get("eligible_counts") or {}).get(horizon, 0)),
            )
            for _group, snapshot in pairs
        )
        for horizon in ("1m", "3m", "6m", "12m")
    }
    calculation_duration = (
        (pairs[0][1].metadata_json or {}).get("calculation_duration_seconds")
        if pairs
        else None
    )
    top = sorted(ranked, key=lambda row: row["rank"] or 10**9)[:10]
    bottom = sorted(ranked, key=lambda row: row["rank"] or 0, reverse=True)[:10]
    gainers_5d = sorted(
        [row for row in ranked if row["rank_change_5d"] is not None],
        key=lambda row: row["rank_change_5d"],
        reverse=True,
    )[:10]
    gainers_20d = sorted(
        [row for row in ranked if row["rank_change_20d"] is not None],
        key=lambda row: row["rank_change_20d"],
        reverse=True,
    )[:10]
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "snapshot_date": ranking["as_of"],
        "benchmark": ranking["benchmark"],
        "weights": INDUSTRY_GROUP_RS_WEIGHTS,
        "min_group_members_for_rs": MIN_GROUP_MEMBERS_FOR_RS,
        "total_groups": len(rows),
        "ranked_groups": len(ranked),
        "small_groups": sum(
            1 for row in rows if int(row["issuer_count"]) < MIN_GROUP_MEMBERS_FOR_RS
        ),
        "insufficient_history_groups": sum(
            1
            for row in rows
            if int(row["issuer_count"]) >= MIN_GROUP_MEMBERS_FOR_RS and not row["is_ranked"]
        ),
        "total_members": sum(int(row["member_count"]) for row in rows),
        "eligible_issuers": sum(int(row["issuer_count"]) for row in rows),
        "missing_1m": missing_by_horizon["1m"],
        "missing_3m": missing_by_horizon["3m"],
        "missing_6m": missing_by_horizon["6m"],
        "missing_12m": missing_by_horizon["12m"],
        "calculation_duration": calculation_duration,
        "top_10_groups": top,
        "bottom_10_groups": bottom,
        "largest_rank_gainers_5d": gainers_5d,
        "largest_rank_gainers_20d": gainers_20d,
    }
