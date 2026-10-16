"""Public calculation identity and stable screening criterion identifiers."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from app.domain.stocks import assessment

# Keys are persisted identifiers; display wording may change through aliases.
CRITERIA = {
    "RS-Bewertung >=80": "rs_rating_80", "RS-Bewertung >=90": "rs_rating_90",
    "RS-Linie über 21-EMA": "rs_above_ema21", "RS-Linie über 50-SMA": "rs_above_sma50",
    "RS-Linie steigt über 5 Wochen": "rs_rising_5w", "RS-Linie steigt über 13 Wochen": "rs_rising_13w",
    "RS-Linie nahe 52W-Hoch": "rs_near_52w_high", "MA-Ordnung (21>50>200)": "ma_order_21_50_200",
    "Fundamental-Datenquelle": "fundamental_source", "Operative Fundamentalkriterien": "operating_fundamentals",
    "EPS-Wachstum letzte 3 Quartale jeweils >=20% YoY": "eps_quarters_20",
    "EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY": "eps_years_20",
    "Umsatz-Wachstum letzte 3 Quartale jeweils >=20% YoY": "revenue_quarters_20",
    "Umsatz-Wachstum letzte 3 Jahre jeweils >=20% YoY": "revenue_years_20",
    "ROE >=17% über letzte 3 Jahre": "roe_years_17",
}


def criterion_id(label: str) -> str:
    # Unregistered legacy criteria remain explicit and versioned. New/renamed
    # criteria should be registered above, retaining their old identifier.
    return CRITERIA.get(label) or "legacy_v1_" + hashlib.sha256(label.encode()).hexdigest()[:16]


@lru_cache(maxsize=1)
def _rules_revision() -> str:
    return hashlib.sha256(Path(assessment.__file__).read_bytes()).hexdigest()[:12]


def calculation_identity(weights: dict) -> dict:
    rules = _rules_revision()
    normalized = json.loads(json.dumps(weights, sort_keys=True))
    digest = hashlib.sha256(json.dumps([rules, normalized], sort_keys=True).encode()).hexdigest()
    return dict(version="assessment_v2", rules=rules, configuration_hash=digest, weights=normalized)
