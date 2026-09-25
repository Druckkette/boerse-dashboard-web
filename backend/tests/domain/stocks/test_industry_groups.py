from app.domain.stocks.industry_groups import (
    TAXONOMY_VERSION,
    ClassificationFeatures,
    classification_fingerprint,
    curated_rule_match,
    exclusion_reason,
    is_eligible_operating_company,
    normalize_text,
    provider_industry_fallback,
)


def test_taxonomy_version_is_explicit_and_stable():
    assert TAXONOMY_VERSION == "industry_groups_v2"


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


def test_security_name_excludes_preferred_and_capital_trust_rows():
    assert exclusion_reason(
        ClassificationFeatures(
            ticker="BACPL",
            company_name="Bank of America Corporation Non Cumulative Perpetual Conv Pfd Ser L",
            instrument_type="unknown",
        )
    ) == "security_name:non_operating"
    assert exclusion_reason(
        ClassificationFeatures(
            ticker="DDT",
            company_name="Dillard's Capital Trust I",
            instrument_type="unknown",
        )
    ) == "security_name:non_operating"


def test_shell_company_provider_industry_is_excluded():
    features = ClassificationFeatures(
        ticker="SPAC",
        company_name="Example Holdings Inc.",
        industry="Shell Companies",
        instrument_type="operating_company",
    )
    assert not is_eligible_operating_company(features)
    assert exclusion_reason(features) == "provider_industry:shell_company"


def test_sec_sic_6770_is_excluded_even_when_instrument_type_is_unknown():
    features = ClassificationFeatures(
        ticker="SPAC",
        company_name="Example Acquisition Corp.",
        sic_code="6770",
        instrument_type="unknown",
    )
    assert not is_eligible_operating_company(features)
    assert exclusion_reason(features) == "sec_sic:6770"


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


def test_provider_regional_banks_map_to_canonical_group():
    match = curated_rule_match(
        ClassificationFeatures(
            ticker="ABC",
            company_name="Example Bancorp",
            sector="Financial Services",
            industry="Banks - Regional",
            instrument_type="operating_company",
        )
    )
    assert match is not None
    assert match.group_code == "BANKREG"
    assert match.group_name == "Banks – Regional"
    assert match.rule_name == "canonical_provider_industry"


def test_provider_gold_maps_to_canonical_mining_group():
    match = curated_rule_match(
        ClassificationFeatures(
            ticker="GOLDX",
            company_name="Example Mining Inc.",
            sector="Basic Materials",
            industry="Gold",
            instrument_type="operating_company",
        )
    )
    assert match is not None
    assert match.group_code == "GOLD"
    assert match.group_name == "Mining – Gold"


def test_numeric_sic_can_classify_without_provider_industry():
    match = curated_rule_match(
        ClassificationFeatures(
            ticker="MSFT",
            company_name="Example Software Corp.",
            sic_code="7372",
            instrument_type="operating_company",
        )
    )
    assert match is not None
    assert match.group_code == "SOFTAPP"
    assert match.rule_name == "sic_7372"


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
    assert one.confidence == 0.72
