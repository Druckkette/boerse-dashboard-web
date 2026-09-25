from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

TAXONOMY_VERSION = "industry_groups_v1"

EXCLUDED_INSTRUMENT_TYPES = {
    "closed_end_fund", "investment_trust", "etf", "etn", "structured_security",
    "preferred_stock", "warrant", "right", "unit", "other_non_operating_security", "spac",
}


@dataclass(frozen=True)
class ClassificationFeatures:
    ticker: str
    company_name: str = ""
    sector: str = ""
    industry: str = ""
    sic_code: str = ""
    sic_description: str = ""
    instrument_type: str = ""
    exchange: str = ""


@dataclass(frozen=True)
class RuleMatch:
    group_code: str
    group_name: str
    sector: str
    family: str
    confidence: float
    rule_name: str


def normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[-_/]+", " ", text)
    text = re.sub(r"\btechnologies\b", "technology", text)
    text = re.sub(r"\bsemiconductors\b", "semiconductor", text)
    text = re.sub(r"\brestaurants\b", "restaurant", text)
    text = re.sub(r"\bbanks\b", "bank", text)
    text = re.sub(r"\bdevices\b", "device", text)
    text = re.sub(r"\bservices\b", "service", text)
    return re.sub(r"\s+", " ", text).strip()


def classification_fingerprint(features: ClassificationFeatures) -> str:
    raw = "|".join(
        normalize_text(value)
        for value in (
            features.company_name,
            features.sector,
            features.industry,
            features.sic_code,
            features.instrument_type,
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_eligible_operating_company(features: ClassificationFeatures) -> bool:
    kind = normalize_text(features.instrument_type).replace(" ", "_")
    return kind not in EXCLUDED_INSTRUMENT_TYPES


def curated_rule_match(features: ClassificationFeatures) -> RuleMatch | None:
    sector = normalize_text(features.sector)
    industry = normalize_text(features.industry)
    sic = normalize_text(features.sic_description)
    name = normalize_text(features.company_name)
    hay = " | ".join((industry, sic, name))

    rules: list[tuple[str, str, str, str, float, tuple[str, ...]]] = [
        ("SEMIFAB", "Semiconductor – Fabless", "Technology", "Semiconductors", 0.94, ("fabless", "semiconductor design", "integrated circuits design")),
        ("SEMIEQP", "Semiconductor – Equipment", "Technology", "Semiconductors", 0.95, ("semiconductor equipment", "wafer fabrication equipment", "photolithography", "semiconductor machinery")),
        ("SEMIFND", "Semiconductor – Foundry", "Technology", "Semiconductors", 0.95, ("foundry", "wafer foundry")),
        ("SEMIMFG", "Semiconductor – Manufacturing", "Technology", "Semiconductors", 0.89, ("semiconductor", "integrated circuits")),
        ("SOFTSEC", "Software – Security", "Technology", "Software", 0.95, ("cybersecurity", "security software", "network security")),
        ("SOFTDB", "Software – Database", "Technology", "Software", 0.92, ("database software", "database management")),
        ("SOFTDEV", "Software – Development Tools", "Technology", "Software", 0.91, ("developer tools", "development software", "devops")),
        ("SOFTINF", "Software – Infrastructure", "Technology", "Software", 0.88, ("infrastructure software", "cloud infrastructure", "systems software")),
        ("SOFTENT", "Software – Enterprise", "Technology", "Software", 0.87, ("enterprise software", "application software", "business software")),
        ("INTERNETCONTENT", "Internet – Content", "Communication Services", "Internet", 0.88, ("internet content", "online content", "interactive media")),
        ("INTERNETCOM", "Internet – Commerce", "Consumer Discretionary", "Internet", 0.90, ("internet retail", "e commerce", "online marketplace")),
        ("RESTAURANT", "Retail – Restaurants", "Consumer Discretionary", "Retail", 0.94, ("restaurant", "eating places")),
        ("RETAILSPEC", "Retail – Specialty", "Consumer Discretionary", "Retail", 0.88, ("specialty retail", "specialty store")),
        ("RETAILFOOD", "Retail – Food & Grocery", "Consumer Staples", "Retail", 0.90, ("grocery", "supermarket", "food retail")),
        ("AERODEF", "Aerospace & Defense", "Industrials", "Aerospace & Defense", 0.94, ("aerospace", "defense", "guided missile", "aircraft")),
        ("BIOTECH", "Medical – Biotech", "Health Care", "Medical", 0.94, ("biotechnology", "biotech", "biological products")),
        ("MEDDEV", "Medical – Devices", "Health Care", "Medical", 0.93, ("medical device", "surgical instrument", "medical instruments")),
        ("PHARMA", "Medical – Pharmaceuticals", "Health Care", "Medical", 0.92, ("pharmaceutical", "drug manufacturer", "medicinal")),
        ("DIAGNOSTIC", "Medical – Diagnostics & Research", "Health Care", "Medical", 0.89, ("diagnostic", "laboratory", "life sciences tools")),
        ("BANKREG", "Banks – Regional", "Financials", "Banks", 0.92, ("regional bank", "state commercial bank", "national commercial bank")),
        ("BANKDIV", "Banks – Diversified", "Financials", "Banks", 0.88, ("diversified bank", "money center bank")),
        ("CAPMARK", "Finance – Capital Markets", "Financials", "Financial Services", 0.90, ("investment banking", "brokerage", "capital markets")),
        ("ASSETMGR", "Finance – Asset Management", "Financials", "Financial Services", 0.90, ("asset management", "investment management")),
        ("INSPC", "Insurance – Property/Casualty", "Financials", "Insurance", 0.94, ("property casualty", "fire marine casualty insurance")),
        ("INSLIFE", "Insurance – Life", "Financials", "Insurance", 0.92, ("life insurance",)),
        ("OILINT", "Energy – Integrated Oil & Gas", "Energy", "Oil & Gas", 0.91, ("integrated oil", "integrated petroleum")),
        ("OILEP", "Energy – Exploration & Production", "Energy", "Oil & Gas", 0.93, ("exploration production", "crude petroleum natural gas")),
        ("OILSVC", "Energy – Oilfield Services", "Energy", "Oil & Gas", 0.93, ("oilfield service", "drilling service")),
        ("REFINE", "Energy – Refining", "Energy", "Oil & Gas", 0.91, ("refining", "petroleum refining")),
        ("UTILITYELEC", "Utilities – Electric", "Utilities", "Utilities", 0.92, ("electric utility", "electric service")),
        ("UTILITYGAS", "Utilities – Gas", "Utilities", "Utilities", 0.92, ("gas utility", "natural gas distribution")),
        ("UTILITYRENEW", "Utilities – Renewable", "Utilities", "Utilities", 0.88, ("renewable utility", "renewable electricity")),
        ("AUTOMFG", "Auto – Manufacturers", "Consumer Discretionary", "Automotive", 0.91, ("auto manufacturer", "automobile manufacturer", "motor vehicles passenger cars")),
        ("AUTOPART", "Auto – Parts", "Consumer Discretionary", "Automotive", 0.90, ("auto parts", "motor vehicle parts")),
        ("TRUCK", "Transportation – Trucking", "Industrials", "Transportation", 0.91, ("trucking", "motor freight")),
        ("AIRLINE", "Transportation – Airlines", "Industrials", "Transportation", 0.94, ("airline", "air transportation scheduled")),
        ("RAIL", "Transportation – Railroads", "Industrials", "Transportation", 0.94, ("railroad", "rail transportation")),
        ("SHIP", "Transportation – Shipping", "Industrials", "Transportation", 0.90, ("marine shipping", "deep sea", "water transportation")),
        ("MACHINERY", "Machinery – Industrial", "Industrials", "Machinery", 0.86, ("industrial machinery", "construction machinery", "farm machinery")),
        ("CONSTEQ", "Construction – Equipment & Materials", "Industrials", "Construction", 0.86, ("construction materials", "building materials", "cement")),
        ("HOMEBLD", "Construction – Homebuilders", "Consumer Discretionary", "Construction", 0.93, ("homebuilder", "operative builders")),
        ("CHEMSPEC", "Chemicals – Specialty", "Materials", "Chemicals", 0.89, ("specialty chemical",)),
        ("CHEMCOMM", "Chemicals – Commodity", "Materials", "Chemicals", 0.85, ("basic chemical", "industrial inorganic chemical")),
        ("STEEL", "Metals – Steel", "Materials", "Metals & Mining", 0.93, ("steel", "blast furnaces")),
        ("GOLD", "Mining – Gold", "Materials", "Metals & Mining", 0.94, ("gold ore", "gold mining")),
        ("COPPER", "Mining – Copper", "Materials", "Metals & Mining", 0.94, ("copper",)),
        ("REITIND", "Real Estate – Industrial REIT", "Real Estate", "REIT", 0.90, ("industrial reit",)),
        ("REITDATA", "Real Estate – Data Center REIT", "Real Estate", "REIT", 0.92, ("data center reit",)),
        ("REITRES", "Real Estate – Residential REIT", "Real Estate", "REIT", 0.90, ("residential reit", "apartment reit")),
        ("REITRET", "Real Estate – Retail REIT", "Real Estate", "REIT", 0.90, ("retail reit", "shopping center reit")),
        ("TELECOM", "Telecom – Services", "Communication Services", "Telecom", 0.91, ("telecommunication service", "wireless telecommunications")),
        ("NETWORK", "Computer – Networking", "Technology", "Hardware", 0.90, ("networking equipment", "communications equipment")),
        ("HARDWARE", "Computer – Hardware", "Technology", "Hardware", 0.86, ("computer hardware", "computer storage device", "electronic computers")),
        ("ELECCOMP", "Electronics – Components", "Technology", "Electronics", 0.87, ("electronic components",)),
        ("PAYMENTS", "Finance – Payments", "Financials", "Financial Services", 0.91, ("payment processing", "transaction processing")),
        ("CREDIT", "Finance – Consumer Credit", "Financials", "Financial Services", 0.88, ("consumer lending", "personal credit")),
        ("HOTEL", "Leisure – Hotels & Resorts", "Consumer Discretionary", "Leisure", 0.91, ("hotel", "resort")),
        ("GAMING", "Leisure – Gaming", "Consumer Discretionary", "Leisure", 0.90, ("casino", "gaming")),
        ("BEVERAGE", "Food – Beverages", "Consumer Staples", "Food & Beverage", 0.88, ("beverage", "soft drinks")),
        ("FOOD", "Food – Packaged", "Consumer Staples", "Food & Beverage", 0.86, ("packaged food", "food preparations")),
        ("HOUSEHOLD", "Consumer – Household Products", "Consumer Staples", "Consumer Products", 0.88, ("household products", "soap detergent")),
    ]

    for code, group, default_sector, family, confidence, patterns in rules:
        if any(pattern in hay for pattern in patterns):
            return RuleMatch(code, group, features.sector or default_sector, family, confidence, code.lower())
    return None


def provider_industry_fallback(features: ClassificationFeatures) -> RuleMatch | None:
    industry = str(features.industry or "").strip()
    if not industry:
        return None
    clean = re.sub(r"\s+", " ", industry.replace("&", "&")).strip()
    code = "PROV_" + hashlib.sha1(normalize_text(clean).encode("utf-8")).hexdigest()[:10].upper()
    sector = str(features.sector or "").strip() or "Unclassified"
    return RuleMatch(
        code,
        clean,
        sector,
        clean,
        0.78,
        "provider_industry_exact",
    )
