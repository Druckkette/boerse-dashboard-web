from __future__ import annotations

from dataclasses import dataclass


MARGIN_DEBT_WARNING_THRESHOLD_PCT = 55.0


@dataclass(frozen=True)
class MarginDebtSnapshot:
    as_of: str
    debit_balance: float
    free_credit_cash: float
    free_credit_margin: float
    margin_debt_ratio_pct: float
    warning_active: bool
    status: str
    detail: str
    source: str = "FINRA"


def evaluate_margin_debt(
    *,
    as_of: str,
    debit_balance: float,
    free_credit_cash: float,
    free_credit_margin: float,
    warning_threshold_pct: float = MARGIN_DEBT_WARNING_THRESHOLD_PCT,
) -> MarginDebtSnapshot:
    total_credit = max(0.0, float(free_credit_cash)) + max(0.0, float(free_credit_margin))
    debit = max(0.0, float(debit_balance))
    denominator = debit + total_credit
    ratio = debit / denominator * 100 if denominator > 0 else 0.0
    warning_active = ratio >= warning_threshold_pct
    status = "Warnsignal" if warning_active else "Unauffällig"
    detail = (
        f"Margin Debt {ratio:.1f}% der FINRA-Kundensalden "
        f"(Debit {debit:,.0f}, Free Credit {total_credit:,.0f}; Schwelle {warning_threshold_pct:.0f}%)."
    )
    return MarginDebtSnapshot(
        as_of=as_of,
        debit_balance=round(debit, 2),
        free_credit_cash=round(max(0.0, float(free_credit_cash)), 2),
        free_credit_margin=round(max(0.0, float(free_credit_margin)), 2),
        margin_debt_ratio_pct=round(ratio, 2),
        warning_active=warning_active,
        status=status,
        detail=detail,
    )
