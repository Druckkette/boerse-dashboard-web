"""CashFlow amounts are positive; their kind determines the direction."""


def cash_flow_sign(kind: str) -> int:
    return -1 if kind in {"withdrawal", "fee", "tax"} else 1
