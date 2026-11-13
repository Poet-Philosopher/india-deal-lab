import pytest

from deal_lab.data import sample_universe
from deal_lab.dcf import default_inputs
from deal_lab.lbo import LBOInputs


@pytest.fixture
def target():
    return sample_universe()["SAMPLE-A"]


@pytest.fixture
def dcf_inputs(target):
    return default_inputs(target)


def make_lbo(target, dcf_in, entry_multiple=None, hold=5):
    em = entry_multiple or (target.enterprise_value / target.ltm_ebitda) * 1.2
    return LBOInputs(
        revenue0=dcf_in.base_revenue, ebitda0=target.ltm_ebitda, growth=dcf_in.growth,
        ebitda_margin=dcf_in.ebitda_margin, da_pct=dcf_in.da_pct, capex_pct=dcf_in.capex_pct,
        nwc_pct_incr=dcf_in.nwc_pct_incr, tax_rate=dcf_in.tax_rate, entry_multiple=em,
        senior_x=3.0, mezz_x=1.0, senior_rate=0.105, mezz_cash_rate=0.11, mezz_pik_rate=0.03,
        fee_pct=0.02, min_cash=0.01 * dcf_in.base_revenue, amort_pct=0.05, sweep_pct=0.75,
        exit_multiple=em, hold_years=hold,
    )


@pytest.fixture
def lbo_inputs(target, dcf_inputs):
    return make_lbo(target, dcf_inputs)
