import math
from dataclasses import replace

import pytest

from deal_lab.dcf import DCFInputs, compute_wacc, run_dcf, sensitivity_wacc_g


def flat(**kw):
    base = dict(base_revenue=100.0, growth=[0.0] * 5, ebitda_margin=[0.2] * 5, da_pct=0.0,
                capex_pct=0.0, nwc_pct_incr=0.0, tax_rate=0.0, wacc=0.10, terminal_growth=0.0,
                exit_multiple=10.0, net_debt=0.0, shares=1.0)
    base.update(kw)
    return DCFInputs(**base)


def test_flat_perpetuity_matches_closed_form():
    # 20 per year forever at 10% is worth exactly 200, both TV methods.
    r = run_dcf(flat())
    assert r["sum_pv_fcff"] == pytest.approx(20 * (1 - 1.1 ** -5) / 0.1)
    assert r["ev_gordon"] == pytest.approx(200.0)
    assert r["ev_exit"] == pytest.approx(200.0)
    assert r["price_gordon"] == pytest.approx(200.0)


def test_mid_year_gordon_is_scaled_by_half_year():
    r = run_dcf(flat(mid_year=True))
    assert r["ev_gordon"] == pytest.approx(200.0 * 1.1 ** 0.5)


def test_hand_computed_fcff_one_year():
    i = flat(growth=[0.10], ebitda_margin=[0.20], da_pct=0.03, capex_pct=0.04,
             nwc_pct_incr=0.10, tax_rate=0.25)
    r = run_dcf(i)
    p = r["projection"]
    assert p["revenue"][0] == pytest.approx(110.0)
    assert p["ebitda"][0] == pytest.approx(22.0)
    assert p["ebit"][0] == pytest.approx(18.7)
    assert p["fcff"][0] == pytest.approx(11.925)


def test_net_debt_and_shares_flow_to_price():
    r = run_dcf(flat(net_debt=50.0, shares=2.0))
    assert r["price_gordon"] == pytest.approx((200.0 - 50.0) / 2.0)


def test_wacc_must_exceed_growth():
    r = run_dcf(flat(wacc=0.04, terminal_growth=0.05))
    assert math.isnan(r["price_gordon"])
    assert not math.isnan(r["price_exit"])


def test_sensitivity_monotonic(dcf_inputs):
    df = sensitivity_wacc_g(dcf_inputs, [0.10, 0.11, 0.12], [0.04, 0.05])
    assert df.iloc[0, 0] > df.iloc[2, 0]  # higher WACC -> lower value
    assert df.iloc[0, 1] > df.iloc[0, 0]  # higher g -> higher value


def test_compute_wacc():
    w = compute_wacc(rf=0.07, erp=0.06, beta=1.0, size_premium=0.0, pre_tax_kd=0.10,
                     tax_rate=0.25, debt_weight=0.2)
    assert w["cost_of_equity"] == pytest.approx(0.13)
    assert w["wacc"] == pytest.approx(0.13 * 0.8 + 0.10 * 0.75 * 0.2)


def test_default_inputs_are_sane(dcf_inputs, target):
    assert dcf_inputs.base_revenue == target.ltm_revenue
    assert all(0.04 <= g <= 0.20 for g in dcf_inputs.growth)
    assert dcf_inputs.wacc > dcf_inputs.terminal_growth
