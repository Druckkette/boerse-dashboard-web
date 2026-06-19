from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
import requests

from app.domain.market.margin_debt import MarginDebtSnapshot, evaluate_margin_debt


FINRA_MARGIN_STATISTICS_XLSX_URL = "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"


class FinraMarginDebtUnavailable(RuntimeError):
    pass


def fetch_latest_margin_debt_snapshot(*, timeout: float = 20.0) -> MarginDebtSnapshot:
    try:
        response = requests.get(FINRA_MARGIN_STATISTICS_XLSX_URL, timeout=timeout)
        response.raise_for_status()
        frame = pd.read_excel(BytesIO(response.content), engine="openpyxl")
    except Exception as exc:  # pragma: no cover - covered by service fallback behavior
        raise FinraMarginDebtUnavailable(str(exc)) from exc

    try:
        return latest_margin_debt_from_frame(frame)
    except Exception as exc:
        raise FinraMarginDebtUnavailable(f"FINRA margin spreadsheet could not be parsed: {exc}") from exc


def latest_margin_debt_from_frame(frame: pd.DataFrame) -> MarginDebtSnapshot:
    if frame.empty:
        raise ValueError("empty spreadsheet")

    normalized_columns = {_normalize_column(column): column for column in frame.columns}
    month_col = _find_column(normalized_columns, ["yearmonth", "month"])
    debit_col = _find_column(normalized_columns, ["debitbalancesincustomerssecuritiesmarginaccounts", "debitbalances"])
    cash_col = _find_column(normalized_columns, ["freecreditbalancesincustomerscashaccounts"])
    margin_col = _find_column(normalized_columns, ["freecreditbalancesincustomerssecuritiesmarginaccounts"])

    clean = frame[[month_col, debit_col, cash_col, margin_col]].dropna(subset=[month_col, debit_col]).copy()
    if clean.empty:
        raise ValueError("no rows with margin debt values")

    clean["_parsed_month"] = pd.to_datetime(clean[month_col], errors="coerce")
    clean = clean.dropna(subset=["_parsed_month"]).sort_values("_parsed_month")
    if clean.empty:
        raise ValueError("no parseable Year-Month values")

    latest = clean.iloc[-1]
    return evaluate_margin_debt(
        as_of=str(latest[month_col]),
        debit_balance=_float(latest[debit_col]),
        free_credit_cash=_float(latest[cash_col]),
        free_credit_margin=_float(latest[margin_col]),
    )


def _find_column(normalized_columns: dict[str, Any], candidates: list[str]) -> Any:
    for candidate in candidates:
        if candidate in normalized_columns:
            return normalized_columns[candidate]
    for candidate in candidates:
        for normalized, original in normalized_columns.items():
            if candidate in normalized:
                return original
    raise ValueError(f"missing column matching {', '.join(candidates)}")


def _normalize_column(value: Any) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def _float(value: Any) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return 0.0
    return float(parsed)
