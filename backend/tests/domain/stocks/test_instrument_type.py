from app.domain.stocks.instrument_type import classify_instrument


def test_registered_closed_end_fund_forms_override_corporate_name():
    assert classify_instrument(
        ticker="DXYZ",
        name="Destiny Tech100 Inc.",
        sec_forms=["N-CEN", "N-2"],
        previous_type="operating_company",
    ) == "closed_end_fund"


def test_registered_fund_with_ncsr_is_closed_end_fund():
    assert classify_instrument(
        ticker="ASA",
        name="ASA Gold and Precious Metals Limited",
        sec_forms=["N-CSR"],
        previous_type="operating_company",
    ) == "closed_end_fund"


def test_bdc_with_periodic_exchange_act_reports_remains_operating_company():
    assert classify_instrument(
        ticker="BBDC",
        name="Barings BDC, Inc.",
        sec_forms=["N-2", "10-K", "10-Q"],
        previous_type="operating_company",
    ) == "operating_company"


def test_audited_royalty_trusts_are_non_operating():
    assert classify_instrument(
        ticker="MSB",
        name="Mesabi Trust Common Stock",
        previous_type="unknown",
    ) == "investment_trust"
    assert classify_instrument(
        ticker="NRT",
        name="North European Oil Royality Trust Common Stock",
        previous_type="unknown",
    ) == "investment_trust"
