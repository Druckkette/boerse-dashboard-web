from app.domain.stocks.industry_groups import (
    TAXONOMY_VERSION,
    ClassificationFeatures,
    classification_fingerprint,
    curated_rule_match,
    is_eligible_operating_company,
    normalize_text,
    provider_industry_fallback,
)


def test_taxonomy_version_is_explicit_and_stable():
    assert TAXONOMY_VERSION == "industry_groups_v1"


def test_normalization_collapses_common_provider_variants():
    assert normalize_text("Semiconductors & Related Devices") == "semiconductor and related device"
    assert normalize_text("Semiconductor-and-Related-Devices") == "semiconductor and related device"


def test_fingerprint_is_deterministic_and_changes_on_classification_metadata():
    base = ClassificationFeatures(
        ticker="XYZ",
        company_name="Example Inc.",
        sector="Technology",
        industry="Application Software",
        sic_code="7372",
        instrument_type="operating_company",
    )
    assert classification_fingerprint(base) == classification_fingerprint(base)

    changed = ClassificationFeatures(
        ticker="XYZ",
        company_name="Example Inc.",
        sector="Technology",
        industry="Security Software",
        sic_code="7372",
        instrument_type="operating_company",
    )
    assert classification_fingerprint(base) != classification_fingerprint(changed)


def test_non_operating_instruments_are_excluded():
    for kind in (
        "etf",
        "closed_end_fund",
        "investment_trust",
        "spac",
        "warrant",
        "preferred_stock",
        "right",
        "unit",
        "structured_security",
    ):
        assert not is_eligible_operating_company(
            ClassificationFeatures(ticker="X", instrument_type=kind)
        )


def test_foreign_private_issuer_is_eligible():
    assert is_eligible_operating_company(
        ClassificationFeatures(ticker="ASML", instrument_type="foreign_private_issuer")
    )


def test_semiconductor_equipment_rule_is_deterministic():
    features = ClassificationFeatures(
        ticker="LRCX",
        company_name="Lam Research Corporation",
        sector="Technology",
        industry="Semiconductor Equipment & Materials",
        sic_description="Special Industry Machinery",
        instrument_type="operating_company",
    )
    first = curated_rule_match(features)
    second = curated_rule_match(features)
    assert first is not None
    assert first == second
    assert first.group_code == "SEMIEQP"
    assert first.group_name == "Semiconductor – Equipment"


def test_security_software_rule():
    match = curated_rule_match(
        ClassificationFeatures(
            ticker="PANW",
            company_name="Palo Alto Networks Inc.",
            sector="Technology",
            industry="Security Software",
            instrument_type="operating_company",
        )
    )
    assert match is not None
    assert match.group_code == "SOFTSEC"


def test_provider_industry_fallback_is_stable():
    features = ClassificationFeatures(
        ticker="ABC",
        company_name="Example Corporation",
        sector="Industrials",
        industry="Waste Management",
        instrument_type="operating_company",
    )
    one = provider_industry_fallback(features)
    two = provider_industry_fallback(features)
    assert one is not None
    assert one == two
    assert one.group_code.startswith("PROV_")
    assert one.confidence == 0.78
