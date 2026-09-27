from datetime import date, timedelta

from app.repositories.industry_group_rs import GroupMemberRow, PricePoint
from app.services import industry_group_rs as service


def _member(ticker: str, group_id: str, *, cik: str = "") -> GroupMemberRow:
    return GroupMemberRow(
        group_id=group_id,
        group_code=group_id.upper(),
        group_name=group_id,
        sector="Technology",
        industry_family="Software",
        instrument_id=f"id-{ticker}",
        ticker=ticker,
        name=f"{ticker} Holdings Class A Common Stock",
        isin="",
        metadata_json={"primary_cik": cik} if cik else {},
    )


def _prices(start: float, daily_return: float, count: int = 280) -> list[PricePoint]:
    first = date(2025, 1, 2)
    value = start
    rows = []
    for index in range(count):
        if index:
            value *= 1.0 + daily_return
        rows.append(
            PricePoint(
                date=first + timedelta(days=index),
                close=value,
                volume=1_000_000,
            )
        )
    return rows


def test_percentiles_map_weakest_to_one_and_strongest_to_100():
    result = service._percentiles({"A": -5.0, "B": 0.0, "C": 10.0})
    assert result["A"] == 1.0
    assert result["C"] == 100.0
    assert 1.0 < result["B"] < 100.0


def test_issuer_dedup_uses_one_representative_for_multiple_share_classes():
    members = [
        _member("AAA", "g1", cik="000123"),
        _member("AAB", "g1", cik="000123"),
        _member("BBB", "g1", cik="000456"),
    ]
    as_of = _prices(100, 0.001)[-1].date
    history = {
        "AAA": _prices(100, 0.001),
        "AAB": _prices(100, 0.001),
        "BBB": _prices(100, 0.002),
    }
    reps, mapping = service._representatives(members, history, as_of)
    assert len(reps) == 2
    assert mapping["AAA"] == mapping["AAB"]


def test_groups_below_minimum_keep_returns_but_have_no_official_rank():
    benchmark = _prices(100, 0.0005)
    as_of = benchmark[-1].date
    members = [_member(f"S{index}", "small") for index in range(4)]
    history = {row.ticker: _prices(100 + index, 0.001) for index, row in enumerate(members)}
    raw = service._raw_group_data(
        {"small": members},
        history,
        benchmark,
        as_of,
        include_performance_series=False,
    )
    service._rank_raw(raw)
    assert raw["small"]["returns"]["3m"] is not None
    assert raw["small"]["is_ranked"] is False
    assert raw["small"]["rank"] is None
    assert raw["small"]["rs_score"] is None


def test_composite_rs_uses_configured_weights():
    raw = {}
    benchmark = _prices(100, 0.0001)
    as_of = benchmark[-1].date
    history = {}
    for group_index, daily_return in enumerate((0.0002, 0.0005, 0.001), start=1):
        members = [_member(f"G{group_index}{member_index}", f"g{group_index}") for member_index in range(5)]
        for member in members:
            history[member.ticker] = _prices(100, daily_return)
        raw.update(
            service._raw_group_data(
                {f"g{group_index}": members},
                history,
                benchmark,
                as_of,
                include_performance_series=False,
            )
        )
    service._rank_raw(raw)
    assert raw["g3"]["rank"] == 1
    assert raw["g3"]["rs_score"] == 100.0
    assert raw["g1"]["rank"] == 3


def test_performance_series_starts_at_100():
    members = [_member(f"P{index}", "perf") for index in range(5)]
    history = {member.ticker: _prices(100, 0.001) for member in members}
    benchmark = _prices(100, 0.0005)
    series = service._performance_series(members, history, benchmark, benchmark[-1].date)
    assert series[0]["group_index"] == 100.0
    assert series[0]["benchmark_index"] == 100.0
    assert series[-1]["group_index"] > series[-1]["benchmark_index"]


def test_percentiles_assign_same_value_to_tied_returns():
    result = service._percentiles({"A": 5.0, "B": 5.0, "C": 10.0})
    assert result["A"] == result["B"]
    assert result["C"] == 100.0


def test_returns_require_a_bar_on_the_snapshot_date():
    points = _prices(100, 0.001, count=40)
    stale_as_of = points[-1].date + timedelta(days=1)
    assert service._return_pct(points, stale_as_of, 21) is None
    assert service._latest_close(points, stale_as_of) is None
    assert service._average_dollar_volume(points, stale_as_of) == 0.0


def test_member_metrics_include_one_week_return():
    member = _member("WEEK", "g1")
    points = _prices(100, 0.001, count=40)
    metrics = service._member_metrics(
        [member],
        [member],
        {"WEEK": "WEEK"},
        {"WEEK": points},
        points[-1].date,
    )
    assert metrics[0]["return_1w"] is not None


def test_composite_ties_share_the_same_official_rank():
    benchmark = _prices(100, 0.0001)
    as_of = benchmark[-1].date
    raw = {}
    history = {}
    for group_id in ("tie-a", "tie-b"):
        members = [_member(f"{group_id}-{index}", group_id) for index in range(5)]
        for member in members:
            history[member.ticker] = _prices(100, 0.001)
        raw.update(
            service._raw_group_data(
                {group_id: members},
                history,
                benchmark,
                as_of,
                include_performance_series=False,
            )
        )
    weak_members = [_member(f"weak-{index}", "weak") for index in range(5)]
    for member in weak_members:
        history[member.ticker] = _prices(100, 0.0002)
    raw.update(
        service._raw_group_data(
            {"weak": weak_members},
            history,
            benchmark,
            as_of,
            include_performance_series=False,
        )
    )
    service._rank_raw(raw)
    assert raw["tie-a"]["rank"] == raw["tie-b"]["rank"] == 1
    assert raw["weak"]["rank"] == 3



def test_winsorized_mean_limits_single_extreme_outlier():
    values = [0.01] * 19 + [10.0]
    robust = service._winsorized_mean(values)
    plain = sum(values) / len(values)
    assert robust is not None
    assert robust < plain
    assert robust < 0.1


def test_group_horizon_return_matches_canonical_series():
    members = [_member(f"C{index}", "canonical") for index in range(5)]
    history = {
        member.ticker: _prices(100 + index, 0.001 + index * 0.0001)
        for index, member in enumerate(members)
    }
    benchmark = _prices(100, 0.0005)
    as_of = benchmark[-1].date
    raw = service._raw_group_data(
        {"canonical": members},
        history,
        benchmark,
        as_of,
        include_performance_series=True,
    )
    series = raw["canonical"]["performance_series"]
    assert raw["canonical"]["returns"]["3m"] == service._series_return_pct(
        series,
        as_of,
        service.HORIZON_SESSIONS["3m"],
    )


def test_top_members_require_current_price_and_assessment():
    members = [
        {"ticker": "AAA", "latest_close": None, "overall_score": 99},
        {"ticker": "BBB", "latest_close": 10.0, "overall_score": None},
        {"ticker": "CCC", "latest_close": 20.0, "overall_score": 80},
        {"ticker": "DDD", "latest_close": 30.0, "overall_score": 70},
    ]
    assert [item["ticker"] for item in service._top_members(members)] == ["CCC", "DDD"]
