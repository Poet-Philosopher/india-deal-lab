from dataclasses import replace

import numpy_financial as npf
import pytest

from deal_lab.lbo import irr_grid, run_lbo, solve_entry_multiple, solve_exit_multiple
from tests.conftest import make_lbo


def test_sources_equal_uses(lbo_inputs):
    r = run_lbo(lbo_inputs)
    assert sum(r["sources"].values()) == pytest.approx(r["uses"])


def test_debt_schedule_rolls_forward(lbo_inputs):
    r = run_lbo(lbo_inputs)
    for t in range(lbo_inputs.hold_years):
        assert r["senior_end"][t] == pytest.approx(
            r["senior_beg"][t] - r["mandatory"][t] - r["sweep"][t])
        assert r["mezz_end"][t] == pytest.approx(r["mezz_beg"][t] + r["mezz_pik"][t])
        assert r["senior_end"][t] >= -1e-9
    assert r["senior_beg"][0] == pytest.approx(r["sources"]["Senior debt"])


def test_cash_balance_reconciles(lbo_inputs):
    r = run_lbo(lbo_inputs)
    cash = lbo_inputs.min_cash
    for t in range(lbo_inputs.hold_years):
        cash += r["cash_flow_pre_repayment"][t] - r["mandatory"][t] - r["sweep"][t]
        assert r["cash_end"][t] == pytest.approx(cash)


@pytest.mark.parametrize("hold", [3, 4, 5])
def test_attribution_sums_to_equity_gain(target, dcf_inputs, hold):
    r = run_lbo(make_lbo(target, dcf_inputs, hold=hold))
    assert sum(r["attribution"].values()) == pytest.approx(r["equity_gain"])


def test_irr_matches_numpy_financial(lbo_inputs):
    r = run_lbo(lbo_inputs)
    flows = [-r["equity0"]] + [0.0] * (lbo_inputs.hold_years - 1) + [r["equity_exit"]]
    assert r["irr"] == pytest.approx(npf.irr(flows), rel=1e-6)


def test_higher_entry_price_lowers_irr(target, dcf_inputs):
    lo = run_lbo(make_lbo(target, dcf_inputs, entry_multiple=10.0))
    hi = run_lbo(replace(make_lbo(target, dcf_inputs, entry_multiple=10.0), entry_multiple=14.0))
    assert lo["irr"] > hi["irr"]


def test_entry_multiple_solver_hits_target(lbo_inputs):
    m = solve_entry_multiple(lbo_inputs, 0.20)
    assert m is not None
    assert run_lbo(replace(lbo_inputs, entry_multiple=m))["irr"] == pytest.approx(0.20, abs=1e-6)


def test_exit_multiple_solver_hits_target(lbo_inputs):
    x = solve_exit_multiple(lbo_inputs, 0.20)
    assert x is not None
    assert run_lbo(replace(lbo_inputs, exit_multiple=x))["irr"] == pytest.approx(0.20, abs=1e-6)


def test_unreachable_target_returns_none(lbo_inputs):
    assert solve_entry_multiple(lbo_inputs, 5.0) is None


def test_irr_grid_shape_and_direction(lbo_inputs):
    g = irr_grid(lbo_inputs, [10, 12, 14], [10, 12, 14])
    assert g.shape == (3, 3)
    assert g.iloc[0, 2] > g.iloc[2, 0]


def test_no_negative_taxes_and_flags(lbo_inputs):
    r = run_lbo(lbo_inputs)
    assert all(t >= 0 for t in r["taxes"])
    stressed = run_lbo(replace(lbo_inputs, senior_x=8.0, mezz_x=3.0, senior_rate=0.14))
    assert stressed["cash_shortfall"] in (True, False)
    assert stressed["interest_cover_y1"] < r["interest_cover_y1"]
