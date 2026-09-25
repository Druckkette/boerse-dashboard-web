from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

TAXONOMY_VERSION = "industry_groups_v3"

EXCLUDED_INSTRUMENT_TYPES = {
    "closed_end_fund",
    "investment_trust",
    "etf",
    "etn",
    "structured_security",
    "preferred_stock",
    "warrant",
    "right",
    "unit",
    "other_non_operating_security",
    "spac",
}

_NON_OPERATING_NAME_PATTERNS = (
    r"\bpreferred\b",
    r"\bpreference shares?\b",
    r"\bpfd\b",
    r"\bdepositary shares?\b",
    r"\bdep(?:ositary)? shs\b",
    r"\bperpetual non cumulative\b",
    r"\btrust certificates?\b",
    r"\btrust preference securities?\b",
    r"\bcorp backed tr certs?\b",
    r"\bcapital trust\b",
    r"\bsce trust\s+[ivx]+\b",
    r"\b(?:gold|silver|commodity|bitcoin|ether(?:eum)?) trust\b",
    r"\b\d+(?:\.\d+)?%\s+series\s+[a-z]\b",
    r"\bzones\b",
)

_SHELL_INDUSTRIES = {
    "shell companies",
    "shell company",
    "blank check",
    "blank check companies",
}

_NON_OPERATING_SIC_CODES = {"6189", "6770"}

# Final production-review overrides for operating companies whose SEC SIC is
# too broad or whose fresh provider profile can legitimately be empty. Each
# entry is guarded by both ticker and a company-name fragment so a future
# ticker reuse cannot inherit the old classification accidentally.
_REVIEWED_COMPANY_RULES: dict[str, tuple[str, str, str, str, str, float]] = {
    "ALPS": ("alps group", "BIOTECH", "Medical – Biotech", "Health Care", "Medical", 0.88),
    "ATCX": (
        "atlas critical minerals",
        "MININGIND",
        "Mining – Diversified & Critical Minerals",
        "Materials",
        "Metals & Mining",
        0.92,
    ),
    "BTTC": ("black titan", "SOFTAPP", "Software – Application", "Technology", "Software", 0.90),
    "DPU": (
        "top kingwin",
        "BUSSERV",
        "Commercial – Business Services",
        "Industrials",
        "Business Services",
        0.90,
    ),
    "FISV": ("fiserv", "PAYMENTS", "Finance – Payments", "Financials", "Financial Services", 0.97),
    "LION": (
        "lionsgate studios",
        "ENTERTAIN",
        "Media – Entertainment",
        "Communication Services",
        "Media & Entertainment",
        0.96,
    ),
    "NIQ": (
        "niq global intelligence",
        "ITSVC",
        "Computer – IT Services",
        "Technology",
        "IT Services",
        0.93,
    ),
}

# Exact provider industries that map cleanly onto canonical groups. Keeping
# these explicit prevents semantic duplicates such as "Banks - Regional" and
# "Banks – Regional" from co-existing under different group codes.
_CANONICAL_PROVIDER_INDUSTRIES: dict[str, tuple[str, str, str, str, float]] = {
    "bank regional": ("BANKREG", "Banks – Regional", "Financials", "Banks", 0.94),
    "bank diversified": ("BANKDIV", "Banks – Diversified", "Financials", "Banks", 0.92),
    "software application": ("SOFTAPP", "Software – Application", "Technology", "Software", 0.92),
    "software infrastructure": ("SOFTINF", "Software – Infrastructure", "Technology", "Software", 0.92),
    "gold": ("GOLD", "Mining – Gold", "Materials", "Metals & Mining", 0.94),
    "reit residential": ("REITRES", "Real Estate – Residential REIT", "Real Estate", "REIT", 0.93),
    "reit industrial": ("REITIND", "Real Estate – Industrial REIT", "Real Estate", "REIT", 0.93),
    "reit retail": ("REITRET", "Real Estate – Retail REIT", "Real Estate", "REIT", 0.93),
    "insurance property and casualty": (
        "INSPC",
        "Insurance – Property/Casualty",
        "Financials",
        "Insurance",
        0.94,
    ),
    "insurance life": ("INSLIFE", "Insurance – Life", "Financials", "Insurance", 0.93),
    "oil and gas e and p": (
        "OILEP",
        "Energy – Exploration & Production",
        "Energy",
        "Oil & Gas",
        0.94,
    ),
    "oil and gas integrated": (
        "OILINT",
        "Energy – Integrated Oil & Gas",
        "Energy",
        "Oil & Gas",
        0.93,
    ),
    "oil and gas equipment and service": (
        "OILSVC",
        "Energy – Oilfield Services",
        "Energy",
        "Oil & Gas",
        0.93,
    ),
    "utilities renewable": (
        "UTILITYRENEW",
        "Utilities – Renewable",
        "Utilities",
        "Utilities",
        0.91,
    ),
    "telecom service": (
        "TELECOM",
        "Telecom – Services",
        "Communication Services",
        "Telecom",
        0.92,
    ),
    "credit service": (
        "CREDIT",
        "Finance – Consumer Credit",
        "Financials",
        "Financial Services",
        0.89,
    ),
    "residential construction": (
        "HOMEBLD",
        "Construction – Homebuilders",
        "Consumer Discretionary",
        "Construction",
        0.92,
    ),
    "lodging": (
        "HOTEL",
        "Leisure – Hotels & Resorts",
        "Consumer Discretionary",
        "Leisure",
        0.91,
    ),
    "gambling": (
        "GAMING",
        "Leisure – Gaming",
        "Consumer Discretionary",
        "Leisure",
        0.91,
    ),
    "household and personal products": (
        "HOUSEHOLD",
        "Consumer – Household Products",
        "Consumer Staples",
        "Consumer Products",
        0.89,
    ),
    "information technology service": (
        "ITSVC",
        "Computer – IT Services",
        "Technology",
        "IT Services",
        0.90,
    ),
    "specialty business service": (
        "BUSSERV",
        "Commercial – Business Services",
        "Industrials",
        "Business Services",
        0.88,
    ),
    "entertainment": (
        "ENTERTAIN",
        "Media – Entertainment",
        "Communication Services",
        "Media & Entertainment",
        0.90,
    ),
    "other industrial metals and mining": (
        "MININGIND",
        "Mining – Diversified & Critical Minerals",
        "Materials",
        "Metals & Mining",
        0.88,
    ),
}

_SIC_RULES: dict[str, tuple[str, str, str, str, float]] = {
    "2834": ("PHARMA", "Medical – Pharmaceuticals", "Health Care", "Medical", 0.96),
    "2835": ("DIAGNOSTIC", "Medical – Diagnostics & Research", "Health Care", "Medical", 0.96),
    "2836": ("BIOTECH", "Medical – Biotech", "Health Care", "Medical", 0.96),
    "3841": ("MEDDEV", "Medical – Devices", "Health Care", "Medical", 0.96),
    "3842": ("MEDDEV", "Medical – Devices", "Health Care", "Medical", 0.96),
    "3845": ("MEDDEV", "Medical – Devices", "Health Care", "Medical", 0.96),
    "6021": ("BANKREG", "Banks – Regional", "Financials", "Banks", 0.95),
    "6022": ("BANKREG", "Banks – Regional", "Financials", "Banks", 0.95),
    "6211": ("CAPMARK", "Finance – Capital Markets", "Financials", "Financial Services", 0.95),
    "6282": ("ASSETMGR", "Finance – Asset Management", "Financials", "Financial Services", 0.95),
    "6311": ("INSLIFE", "Insurance – Life", "Financials", "Insurance", 0.95),
    "6331": ("INSPC", "Insurance – Property/Casualty", "Financials", "Insurance", 0.95),
    "1311": ("OILEP", "Energy – Exploration & Production", "Energy", "Oil & Gas", 0.95),
    "1381": ("OILSVC", "Energy – Oilfield Services", "Energy", "Oil & Gas", 0.95),
    "1389": ("OILSVC", "Energy – Oilfield Services", "Energy", "Oil & Gas", 0.95),
    "2911": ("REFINE", "Energy – Refining", "Energy", "Oil & Gas", 0.95),
    "4911": ("UTILITYELEC", "Utilities – Electric", "Utilities", "Utilities", 0.95),
    "4924": ("UTILITYGAS", "Utilities – Gas", "Utilities", "Utilities", 0.95),
    "3711": ("AUTOMFG", "Auto – Manufacturers", "Consumer Discretionary", "Automotive", 0.95),
    "3714": ("AUTOPART", "Auto – Parts", "Consumer Discretionary", "Automotive", 0.95),
    "4213": ("TRUCK", "Transportation – Trucking", "Industrials", "Transportation", 0.95),
    "4512": ("AIRLINE", "Transportation – Airlines", "Industrials", "Transportation", 0.95),
    "4011": ("RAIL", "Transportation – Railroads", "Industrials", "Transportation", 0.95),
    "4412": ("SHIP", "Transportation – Shipping", "Industrials", "Transportation", 0.95),
    "1531": ("HOMEBLD", "Construction – Homebuilders", "Consumer Discretionary", "Construction", 0.95),
    "3312": ("STEEL", "Metals – Steel", "Materials", "Metals & Mining", 0.95),
    "1041": ("GOLD", "Mining – Gold", "Materials", "Metals & Mining", 0.96),
    "1021": ("COPPER", "Mining – Copper", "Materials", "Metals & Mining", 0.96),
    "4813": ("TELECOM", "Telecom – Services", "Communication Services", "Telecom", 0.95),
    "3661": ("NETWORK", "Computer – Networking", "Technology", "Hardware", 0.94),
    "3571": ("HARDWARE", "Computer – Hardware", "Technology", "Hardware", 0.94),
    "3674": ("SEMIMFG", "Semiconductor – Manufacturing", "Technology", "Semiconductors", 0.96),
    "7370": ("ITSVC", "Computer – IT Services", "Technology", "IT Services", 0.92),
    "7372": ("SOFTAPP", "Software – Application", "Technology", "Software", 0.94),
    "7812": ("ENTERTAIN", "Media – Entertainment", "Communication Services", "Media & Entertainment", 0.95),
    "5812": ("RESTAURANT", "Retail – Restaurants", "Consumer Discretionary", "Retail", 0.95),
    "7011": ("HOTEL", "Leisure – Hotels & Resorts", "Consumer Discretionary", "Leisure", 0.95),
    "2086": ("BEVERAGE", "Food – Beverages", "Consumer Staples", "Food & Beverage", 0.95),
    "2099": ("FOOD", "Food – Packaged", "Consumer Staples", "Food & Beverage", 0.94),
    "2841": ("HOUSEHOLD", "Consumer – Household Products", "Consumer Staples", "Consumer Products", 0.94),
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


def exclusion_reason(features: ClassificationFeatures) -> str:
    kind = normalize_text(features.instrument_type).replace(" ", "_")
    if kind in EXCLUDED_INSTRUMENT_TYPES:
        return f"instrument_type:{kind}"
    sic_code = str(features.sic_code or "").strip()
    if sic_code in _NON_OPERATING_SIC_CODES:
        return f"sec_sic:{sic_code}"
    industry = normalize_text(features.industry)
    if industry in _SHELL_INDUSTRIES or "shell compan" in industry:
        return "provider_industry:shell_company"
    name = normalize_text(features.company_name)
    if any(re.search(pattern, name) for pattern in _NON_OPERATING_NAME_PATTERNS):
        return "security_name:non_operating"
    return ""


def is_eligible_operating_company(features: ClassificationFeatures) -> bool:
    return not exclusion_reason(features)


def _rule_from_tuple(
    definition: tuple[str, str, str, str, float],
    *,
    default_sector: str,
    rule_name: str,
) -> RuleMatch:
    code, group, sector, family, confidence = definition
    return RuleMatch(code, group, sector, family, confidence, rule_name)


def curated_rule_match(features: ClassificationFeatures) -> RuleMatch | None:
    industry = normalize_text(features.industry)
    sic_description = normalize_text(features.sic_description)
    sic_code = str(features.sic_code or "").strip()
    name = normalize_text(features.company_name)

    reviewed = _REVIEWED_COMPANY_RULES.get(str(features.ticker or "").strip().upper())
    if reviewed is not None:
        name_fragment, code, group, sector, family, confidence = reviewed
        if normalize_text(name_fragment) in name:
            return RuleMatch(
                code,
                group,
                features.sector or sector,
                family,
                confidence,
                "reviewed_company_rule",
            )

    canonical = _CANONICAL_PROVIDER_INDUSTRIES.get(industry)
    if canonical is not None:
        return _rule_from_tuple(
            canonical,
            default_sector=features.sector,
            rule_name="canonical_provider_industry",
        )

    hay = " | ".join((industry, sic_description, name))
    rules: list[tuple[str, str, str, str, float, tuple[str, ...]]] = [
        ("SEMIFAB", "Semiconductor – Fabless", "Technology", "Semiconductors", 0.94, ("fabless", "semiconductor design", "integrated circuits design")),
        ("SEMIEQP", "Semiconductor – Equipment", "Technology", "Semiconductors", 0.95, ("semiconductor equipment", "wafer fabrication equipment", "photolithography", "semiconductor machinery")),
        ("SEMIFND", "Semiconductor – Foundry", "Technology", "Semiconductors", 0.95, ("foundry", "wafer foundry")),
        ("SEMIMFG", "Semiconductor – Manufacturing", "Technology", "Semiconductors", 0.89, ("semiconductor", "integrated circuits")),
        ("SOFTSEC", "Software – Security", "Technology", "Software", 0.95, ("cybersecurity", "security software", "network security")),
        ("SOFTDB", "Software – Database", "Technology", "Software", 0.92, ("database software", "database management")),
        ("SOFTDEV", "Software – Development Tools", "Technology", "Software", 0.91, ("developer tools", "development software", "devops")),
        ("SOFTINF", "Software – Infrastructure", "Technology", "Software", 0.88, ("infrastructure software", "cloud infrastructure", "systems software")),
        ("SOFTAPP", "Software – Application", "Technology", "Software", 0.90, ("application software",)),
        ("SOFTENT", "Software – Enterprise", "Technology", "Software", 0.87, ("enterprise software", "business software")),
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
        ("BANKREG", "Banks – Regional", "Financials", "Banks", 0.92, ("regional bank", "bank regional", "state commercial bank", "national commercial bank")),
        ("BANKDIV", "Banks – Diversified", "Financials", "Banks", 0.88, ("diversified bank", "bank diversified", "money center bank")),
        ("CAPMARK", "Finance – Capital Markets", "Financials", "Financial Services", 0.90, ("investment banking", "brokerage", "capital markets")),
        ("ASSETMGR", "Finance – Asset Management", "Financials", "Financial Services", 0.90, ("asset management", "investment management")),
        ("INSPC", "Insurance – Property/Casualty", "Financials", "Insurance", 0.94, ("property casualty", "property and casualty", "fire marine casualty insurance")),
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
        ("REITIND", "Real Estate – Industrial REIT", "Real Estate", "REIT", 0.90, ("industrial reit", "reit industrial")),
        ("REITDATA", "Real Estate – Data Center REIT", "Real Estate", "REIT", 0.92, ("data center reit", "reit data center")),
        ("REITRES", "Real Estate – Residential REIT", "Real Estate", "REIT", 0.90, ("residential reit", "apartment reit", "reit residential")),
        ("REITRET", "Real Estate – Retail REIT", "Real Estate", "REIT", 0.90, ("retail reit", "shopping center reit", "reit retail")),
        ("TELECOM", "Telecom – Services", "Communication Services", "Telecom", 0.91, ("telecommunication service", "telecom service", "wireless telecommunications")),
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
            return RuleMatch(code, group, default_sector, family, confidence, code.lower())

    sic_match = _SIC_RULES.get(sic_code)
    if sic_match is not None:
        return _rule_from_tuple(
            sic_match,
            default_sector=features.sector,
            rule_name=f"sic_{sic_code}",
        )
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
        0.72,
        "provider_industry_exact",
    )
