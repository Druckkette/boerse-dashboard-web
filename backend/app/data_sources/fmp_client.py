from __future__ import annotations

import json
from typing import Any


FMP_BASE_URL = "https://financialmodelingprep.com/stable"


def fmp_endpoint(path: str) -> str:
    return f"{FMP_BASE_URL}/{path.strip('/')}"


FMP_PROFILE_URL = fmp_endpoint("profile")
FMP_INCOME_STATEMENT_URL = fmp_endpoint("income-statement")
FMP_RATIOS_TTM_URL = fmp_endpoint("ratios-ttm")


def compact_fmp_response_body(response: Any, *, limit: int = 500) -> str:
    text = str(getattr(response, "text", "") or "").strip()
    if not text:
        try:
            payload = response.json()
        except Exception:
            payload = None
        if payload is not None:
            text = json.dumps(payload, ensure_ascii=True)
    return text[:limit]


def is_non_empty_fmp_payload(payload: Any) -> bool:
    if isinstance(payload, dict):
        if payload.get("Error Message"):
            return False
        return bool(payload)
    if isinstance(payload, list):
        return bool(payload)
    return False
