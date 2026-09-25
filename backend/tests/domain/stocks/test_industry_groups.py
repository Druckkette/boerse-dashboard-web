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
    assert TAXONOMY_VERSION == "industry_groups_v4"


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


def test_frozen_v4_does_not_create_dynamic_provider_groups():
    features = ClassificationFeatures(
        ticker="ABC",
        company_name="Example Corporation",
        sector="Industrials",
        industry="Brand New Provider Industry",
        instrument_type="operating_company",
    )
    assert provider_industry_fallback(features) is None


def test_v4_provider_industry_gets_stable_canonical_code():
    match = curated_rule_match(
        ClassificationFeatures(
            ticker="WMX",
            company_name="Example Waste Company",
            sector="Industrials",
            industry="Waste Management",
            instrument_type="operating_company",
        )
    )
    assert match is not None
    assert match.group_code == "WASTE"
    assert not match.group_code.startswith("PROV_")


def test_v4_splits_medical_instruments_from_devices():
    match = curated_rule_match(
        ClassificationFeatures(
            ticker="ALGN",
            company_name="Align Technology, Inc.",
            sector="Healthcare",
            industry="Medical Instruments & Supplies",
            instrument_type="operating_company",
        )
    )
    assert match is not None
    assert match.group_code == "MEDINSTR"


def test_v4_splits_industrial_machinery():
    specialty = curated_rule_match(
        ClassificationFeatures(
            ticker="IR",
            company_name="Ingersoll Rand Inc.",
            sector="Industrials",
            industry="Specialty Industrial Machinery",
            instrument_type="operating_company",
        )
    )
    heavy = curated_rule_match(
        ClassificationFeatures(
            ticker="DE",
            company_name="Deere & Company",
            sector="Industrials",
            industry="Farm & Heavy Construction Machinery",
            instrument_type="operating_company",
        )
    )
    assert specialty is not None and specialty.group_code == "MACHSPEC"
    assert heavy is not None and heavy.group_code == "MACHHEAVY"


def test_v4_payment_processors_are_separate_from_consumer_credit():
    payment = curated_rule_match(
        ClassificationFeatures(
            ticker="V",
            company_name="Visa Inc.",
            sector="Financial Services",
            industry="Credit Services",
            instrument_type="operating_company",
        )
    )
    lender = curated_rule_match(
        ClassificationFeatures(
            ticker="AFRM",
            company_name="Affirm Holdings, Inc.",
            sector="Financial Services",
            industry="Credit Services",
            instrument_type="operating_company",
        )
    )
    assert payment is not None and payment.group_code == "PAYPROC"
    assert lender is not None and lender.group_code == "CREDIT"



def test_final_review_operating_companies_are_deterministically_classified():
    cases = [
        ("ALPS", "ALPS Group Inc - Ordinary Share", "8000", "Services-Health Services", "BIOTECH"),
        ("ATCX", "Atlas Critical Minerals Corporation - Common Stock", "1040", "Gold and Silver Ores", "MININGIND"),
        ("BTTC", "Black Titan Corp - Ordinary Shares", "7371", "Services-Computer Programming Services", "SOFTAPP"),
        ("DPU", "Top KingWin Ltd - Class A Ordinary Shares", "7389", "Services-Business Services, NEC", "BUSSERV"),
        ("FISV", "Fiserv, Inc. - Common Stock", "7389", "Services-Business Services, NEC", "PAYPROC"),
        ("LION", "Lionsgate Studios Corp Common Shares", "7812", "Services-Motion Picture & Video Tape Production", "ENTERTAIN"),
        ("NIQ", "NIQ Global Intelligence plc Ordinary Shares", "7370", "Services-Computer Programming, Data Processing, Etc.", "ITSVC"),
    ]
    for ticker, name, sic, sic_description, expected in cases:
        match = curated_rule_match(
            ClassificationFeatures(
                ticker=ticker,
                company_name=name,
                sic_code=sic,
                sic_description=sic_description,
                instrument_type="operating_company",
            )
        )
        assert match is not None, ticker
        assert match.group_code == expected, ticker


def test_final_review_non_operating_securities_are_excluded():
    cases = [
        ("BAR", "GraniteShares Gold Trust Shares of Beneficial Interest", "6221"),
        ("DBRGPH", "DigitalBridge Group, Inc. 7.125% Series H", ""),
        ("DBRGPI", "DigitalBridge Group, Inc. 7.15% Series I", ""),
        ("DBRGPJ", "DigitalBridge Group, Inc. 7.125% Series J", ""),
        ("JBK", "Lehman ABS 3.50 3.50% Adjustable Corp Backed Tr Certs GS Cap I", "6189"),
        ("NLYPF", "Annaly Capital Management Inc 6.95% Series F", ""),
        ("SCEPL", "SCE TRUST VI", ""),
        ("SCEPM", "SCE Trust VII 7.50% Trust Preference Securities", ""),
        ("SCEPN", "SCE Trust VIII 6.95% Trust Preference Securities", ""),
    ]
    for ticker, name, sic in cases:
        features = ClassificationFeatures(
            ticker=ticker,
            company_name=name,
            sic_code=sic,
            instrument_type="unknown",
        )
        assert not is_eligible_operating_company(features), ticker
        assert exclusion_reason(features), ticker


def test_v4_broad_pharma_does_not_recreate_legacy_group():
    match = curated_rule_match(
        ClassificationFeatures(
            ticker="PHRM",
            company_name="Example Pharmaceuticals, Inc.",
            sector="Health Care",
            instrument_type="operating_company",
        )
    )
    assert match is not None
    assert match.group_code == "PHARMA_OTHER"


def test_v4_machinery_split_covers_sec_descriptions():
    heavy = curated_rule_match(
        ClassificationFeatures(
            ticker="HEAVY",
            company_name="Example Equipment Corp.",
            sic_code="3531",
            sic_description="Construction Machinery & Equip",
            instrument_type="operating_company",
        )
    )
    specialty = curated_rule_match(
        ClassificationFeatures(
            ticker="SPEC",
            company_name="Example Automation Corp.",
            sic_code="3569",
            sic_description="General Industrial Machinery & Equipment, NEC",
            instrument_type="operating_company",
        )
    )
    assert heavy is not None and heavy.group_code == "MACHHEAVY"
    assert specialty is not None and specialty.group_code == "MACHSPEC"


def test_v4_gaming_residual_uses_nonlegacy_code():
    other = curated_rule_match(
        ClassificationFeatures(
            ticker="GAME",
            company_name="Example Gaming, Inc.",
            instrument_type="operating_company",
        )
    )
    casino = curated_rule_match(
        ClassificationFeatures(
            ticker="CAS",
            company_name="Example Casino, Inc.",
            instrument_type="operating_company",
        )
    )
    assert other is not None and other.group_code == "GAMEOTHER"
    assert casino is not None and casino.group_code == "CASINO"


def test_v4_beverage_residual_uses_nonlegacy_code():
    generic = curated_rule_match(
        ClassificationFeatures(
            ticker="BEV",
            company_name="Example Beverage Corporation",
            instrument_type="operating_company",
        )
    )
    soft_drink = curated_rule_match(
        ClassificationFeatures(
            ticker="SODA",
            company_name="Example Drinks Corporation",
            sic_code="2086",
            sic_description="Bottled & Canned Soft Drinks & Carbonated Waters",
            instrument_type="operating_company",
        )
    )
    assert generic is not None and generic.group_code == "BEVOTHER"
    assert soft_drink is not None and soft_drink.group_code == "BEVNONALC"


def test_v4_restaurants_and_construction_materials_use_canonical_names():
    restaurant = curated_rule_match(
        ClassificationFeatures(
            ticker="REST",
            company_name="Example Restaurant Group",
            industry="Restaurants",
            instrument_type="operating_company",
        )
    )
    materials = curated_rule_match(
        ClassificationFeatures(
            ticker="MAT",
            company_name="Example Building Materials Inc.",
            industry="Building Materials",
            instrument_type="operating_company",
        )
    )
    assert restaurant is not None
    assert restaurant.group_code == "RESTAURANT"
    assert restaurant.group_name == "Leisure – Restaurants"
    assert restaurant.family == "Leisure"
    assert materials is not None
    assert materials.group_code == "CONSTMAT"
    assert materials.group_name == "Construction – Materials"


def test_v4_mobile_infrastructure_is_real_estate_peer():
    match = curated_rule_match(
        ClassificationFeatures(
            ticker="BEEP",
            company_name="Mobile Infrastructure Corporation - Common Stock",
            industry="Infrastructure Operations",
            instrument_type="operating_company",
        )
    )
    assert match is not None
    assert match.group_code == "REALPARK"
    assert match.sector == "Real Estate"
