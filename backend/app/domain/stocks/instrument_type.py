"""Conservative classification of exchange securities for statement requirements.

Structured exchange flags and SEC filing forms take precedence over names. A
name is only used when it identifies a specific legal/security structure.
"""
from __future__ import annotations

import re

NON_OPERATING_TYPES = frozenset({
    "closed_end_fund", "investment_trust", "etf", "etn", "structured_security",
    "preferred_stock", "warrant", "right", "unit", "other_non_operating_security",
})
# Curated examples retained for older universe rows whose only saved name is
# the symbol. A fresh exchange description or SEC form can replace these.
KNOWN_TICKER_TYPES = {
    **dict.fromkeys(("EVF", "NRK", "NRO", "NMS", "NMZ", "NPV", "ADX", "AFB", "AOD", "ARDC"), "closed_end_fund"),
    **dict.fromkeys(("FNGD", "FNGO"), "etn"),
    **dict.fromkeys(("GJH", "GJO", "GJP", "GJR", "GJS", "GJT", "KTN", "PYT"), "structured_security"),
    **dict.fromkeys(("AAC", "AACI", "AACO", "AACP", "ACAA", "ACGC", "ADAC", "AEAQ"), "spac"),
}


def classify_instrument(*, ticker: str = "", name: str = "", etf: str = "", nextshares: str = "",
                        asset_class: str = "", security_type: str = "",
                        sec_sic: str | int = "",
                        sec_forms: list[str] | None = None,
                        previous_type: str = "") -> str:
    forms = {str(form).upper().removesuffix("/A") for form in sec_forms or []}
    category = f" {security_type.lower()} {asset_class.lower()} "
    title = f" {name.lower()} "
    if etf.upper() == "Y" or nextshares.upper() == "Y" or re.search(r"\b(exchange.traded fund|etf)\b", category + title):
        return "etf"
    if re.search(r"\betns?\b|exchange.traded notes?", category + title):
        return "etn"
    for pattern, kind in (
        (r"\bwarrants?\b", "warrant"),
        (r"\brights?\b", "right"),
        (r"\bunits?\b(?!\s+(corp(oration)?|inc(orporated)?|company|co\.?|limited|ltd\.?))", "unit"),
        (
            r"\bpreferred\b|\bpreference shares?\b|\bpfd\b|\bdepositary shares?\b|"
            r"\bdep(?:ositary)? shs\b|\bperpetual non cumulative\b",
            "preferred_stock",
        ),
        (
            r"\bstructured\b|\btrust certificates?\b|\bindex.linked notes?\b|\bnotes? due\b|"
            r"\bdebentures?\b|\bsynthetic fixed.income securities\b|\bstrats\b|"
            r"\bpplus\b.*\bctf\b|\bcapital trust\b|\bzones\b",
            "structured_security",
        ),
    ):
        if re.search(pattern, category + title):
            return kind
    if str(sec_sic).strip() == "6770":
        return "spac"
    # N-CSR/N-CSRS are certified shareholder reports filed by registered
    # investment companies. They identify funds whose exchange names may
    # contain neither "Fund" nor "Investment Trust".
    if forms & {"N-CSR", "N-CSRS"}:
        return "investment_trust" if re.search(r"\btrust\b", title) else "closed_end_fund"
    if re.search(r"\b(closed.end|municipal (income|bond)|muni (income|bond)|investment fund|income fund|bond fund|mutual fund|fund\b(?!\s+(management|manager|services)))", category + title):
        return "closed_end_fund"
    if re.search(r"\b(investment trust|royalty trust|income trust|unit trust)\b", category + title):
        return "investment_trust"
    if re.search(r"\b(acquisition(?:\s+(?:[ivx]+|[0-9]+))?\s+(?:corp(oration)?|company|co\.?|limited|ltd\.?)|blank.check company|special purpose acquisition|spac)\b", title):
        return "spac"
    if asset_class.lower().strip() in {"bond", "commodity", "currency", "crypto", "index", "fund"}:
        return "other_non_operating_security"
    if (not name.strip() or name.strip().upper() == ticker.strip().upper()) and ticker.upper() in KNOWN_TICKER_TYPES:
        return KNOWN_TICKER_TYPES[ticker.upper()]
    if ("20-F" in forms or "40-F" in forms) and "10-K" in forms:
        return previous_type if previous_type in {"operating_company", "foreign_private_issuer"} else "unknown"
    if "20-F" in forms or "40-F" in forms or ("6-K" in forms and not ({"10-K", "10-Q"} & forms)):
        return "foreign_private_issuer"
    if {"10-K", "10-Q"} & forms:
        return "operating_company"
    if previous_type in NON_OPERATING_TYPES | {"spac", "foreign_private_issuer"}:
        return previous_type
    if re.search(r"\b(corp(oration)?|inc(orporated)?|plc|limited|ltd\.?|company|co\.?)\b", title):
        return "operating_company"
    return "unknown"


def required_histories(instrument_type: str) -> tuple[str, ...]:
    if instrument_type in NON_OPERATING_TYPES or instrument_type == "spac":
        return ()
    annual = ("annual_eps_history", "annual_revenue_history")
    if instrument_type == "foreign_private_issuer":
        return annual
    return ("eps_quarter_history", *annual[:1], "revenue_quarter_history", *annual[1:])


def inapplicable_reason(instrument_type: str) -> str:
    if instrument_type == "spac":
        return "spac_no_operating_history"
    if instrument_type == "other_non_operating_security":
        return "non_operating_security"
    if instrument_type in NON_OPERATING_TYPES:
        return "not_applicable_for_instrument_type"
    return ""
