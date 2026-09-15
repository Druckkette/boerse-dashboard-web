from datetime import date, timedelta

from app.services.freshness import _required_13f_period
from app.services.market_calendar import expected_us_market_session, previous_us_market_session_date


def dependency_quality(fundamentals: dict, institutional: dict, rs: dict, *, today: date | None = None) -> dict[str, dict]:
    today = today or date.today()
    required_period = _required_13f_period(today)[0]
    expected_session = expected_us_market_session().date
    rs_date = previous_us_market_session_date(expected_session) if rs.get("source") != "computed" else expected_session

    def state(value, minimum):
        try:
            return "fresh" if date.fromisoformat(str(value)) >= minimum else "stale"
        except (ValueError, TypeError):
            return "missing"

    histories = (
        ("eps_quarter_history", "eps_current_quarter", "eps_same_quarter_last_year"),
        ("annual_eps_history", "eps_current_year", "eps_previous_year"),
        ("revenue_quarter_history", "revenue_current_quarter", "revenue_same_quarter_last_year"),
        ("annual_revenue_history", "revenue_current_year", "revenue_previous_year"),
    )
    histories_complete = all(
        isinstance(fundamentals.get(key), list) and len(fundamentals[key]) >= 3
        and all(isinstance(item, dict) and item.get(current) is not None and item.get(previous) is not None for item in fundamentals[key][:3])
        for key, current, previous in histories
    )
    report_state = fundamentals.get("report_refresh") or {}
    fundamental_status = state(fundamentals.get("as_of"), today - timedelta(days=14))
    if report_state.get("complete") is False:
        fundamental_status = "stale"
    return {
        "fundamentals": {"status": fundamental_status, "as_of": fundamentals.get("as_of"), "label": "Fundamental-Cache", "expected": report_state.get("expected_period")},
        "institutional": {"status": state(institutional.get("report_period"), required_period), "as_of": institutional.get("report_period"), "expected": required_period.isoformat(), "label": "13F-Berichtsperiode"},
        "rs": {"status": state(rs.get("as_of"), rs_date), "as_of": rs.get("as_of"), "label": "RS-Rating"},
        "rs_line": {"status": state(rs.get("line_as_of"), expected_session) if rs.get("ema21") is not None and rs.get("rs_line_last") is not None else "missing", "as_of": rs.get("line_as_of"), "label": "RS-Linie"},
        "histories": {"status": "fresh" if histories_complete else "missing", "as_of": fundamentals.get("as_of"), "label": "EPS-/Umsatz-Historien (3 Quartale und 3 Jahre)"},
    }
