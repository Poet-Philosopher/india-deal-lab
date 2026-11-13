"""Discounted cash flow valuation (unlevered free cash flow to the firm).

Conventions
-----------
* 5 explicit projection years.
* FCFF = EBIT x (1 - tax) + D&A - capex - increase in NWC.
* NWC change = nwc_pct_incr x change in revenue.
* Terminal value two ways: Gordon growth and exit EV/EBITDA multiple.
* Mid-year toggle: flows discounted at t - 0.5; the Gordon TV is discounted at N - 0.5
  (it capitalises mid-year flows); the exit-multiple TV is discounted at N.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List

import numpy as np
import pandas as pd

from .models import CompanyData

N_YEARS = 5


@dataclass
class DCFInputs:
    base_revenue: float
    growth: List[float]
    ebitda_margin: List[float]
    da_pct: float
    capex_pct: float
    nwc_pct_incr: float
    tax_rate: float
    wacc: float
    terminal_growth: float
    exit_multiple: float
    net_debt: float
    shares: float
    mid_year: bool = False


def compute_wacc(rf: float, erp: float, beta: float, size_premium: float,
                 pre_tax_kd: float, tax_rate: float, debt_weight: float) -> dict:
    ke = rf + beta * erp + size_premium
    kd = pre_tax_kd * (1 - tax_rate)
    wacc = ke * (1 - debt_weight) + kd * debt_weight
    return {"cost_of_equity": ke, "after_tax_cost_of_debt": kd,
            "debt_weight": debt_weight, "wacc": wacc}


def operating_projection(base_revenue, growth, margin, da_pct, capex_pct, nwc_pct, tax_rate):
    rev, ebitda, da, ebit, capex, dnwc, nopat, fcff = ([] for _ in range(8))
    prev = base_revenue
    for g, m in zip(growth, margin):
        r = prev * (1 + g)
        e = r * m
        d = r * da_pct
        b = e - d
        cx = r * capex_pct
        dn = (r - prev) * nwc_pct
        np_ = b * (1 - tax_rate)
        rev.append(r); ebitda.append(e); da.append(d); ebit.append(b)
        capex.append(cx); dnwc.append(dn); nopat.append(np_)
        fcff.append(np_ + d - cx - dn)
        prev = r
    return {"revenue": rev, "ebitda": ebitda, "da": da, "ebit": ebit, "capex": capex,
            "dnwc": dnwc, "nopat": nopat, "fcff": fcff}


def run_dcf(i: DCFInputs) -> dict:
    p = operating_projection(i.base_revenue, i.growth, i.ebitda_margin, i.da_pct,
                             i.capex_pct, i.nwc_pct_incr, i.tax_rate)
    n = len(i.growth)
    shift = 0.5 if i.mid_year else 0.0
    times = [t + 1 - shift for t in range(n)]
    dfs = [(1 + i.wacc) ** -t for t in times]
    pv_fcff = [f * d for f, d in zip(p["fcff"], dfs)]
    sum_pv = float(sum(pv_fcff))

    out = {"projection": p, "times": times, "discount_factors": dfs,
           "pv_fcff": pv_fcff, "sum_pv_fcff": sum_pv}

    if i.wacc > i.terminal_growth:
        tv_g = p["fcff"][-1] * (1 + i.terminal_growth) / (i.wacc - i.terminal_growth)
        pv_tv_g = tv_g / (1 + i.wacc) ** (n - shift)
    else:
        tv_g = pv_tv_g = float("nan")
    tv_x = p["ebitda"][-1] * i.exit_multiple
    pv_tv_x = tv_x / (1 + i.wacc) ** n

    ev_g = sum_pv + pv_tv_g
    ev_x = sum_pv + pv_tv_x
    out.update({
        "tv_gordon": tv_g, "pv_tv_gordon": pv_tv_g, "ev_gordon": ev_g,
        "tv_exit": tv_x, "pv_tv_exit": pv_tv_x, "ev_exit": ev_x,
        "equity_gordon": ev_g - i.net_debt, "equity_exit": ev_x - i.net_debt,
        "price_gordon": (ev_g - i.net_debt) / i.shares,
        "price_exit": (ev_x - i.net_debt) / i.shares,
        "tv_share_gordon": pv_tv_g / ev_g if ev_g == ev_g and ev_g else float("nan"),
        "tv_share_exit": pv_tv_x / ev_x if ev_x else float("nan"),
        "implied_exit_multiple_from_gordon": tv_g / p["ebitda"][-1] if tv_g == tv_g else float("nan"),
        # end-year basis approximation of the growth rate implied by the exit multiple
        "implied_growth_from_exit": (tv_x * i.wacc - p["fcff"][-1]) / (tv_x + p["fcff"][-1]),
    })
    out["price_blended"] = float(np.nanmean([out["price_gordon"], out["price_exit"]]))
    return out


def sensitivity_wacc_g(i: DCFInputs, waccs, gs) -> pd.DataFrame:
    data = [[run_dcf(replace(i, wacc=w, terminal_growth=g))["price_gordon"] for g in gs] for w in waccs]
    return pd.DataFrame(data, index=[f"{w:.1%}" for w in waccs], columns=[f"{g:.1%}" for g in gs])


def sensitivity_wacc_exit(i: DCFInputs, waccs, mults) -> pd.DataFrame:
    data = [[run_dcf(replace(i, wacc=w, exit_multiple=m))["price_exit"] for m in mults] for w in waccs]
    return pd.DataFrame(data, index=[f"{w:.1%}" for w in waccs], columns=[f"{m:.1f}x" for m in mults])


def default_inputs(cd: CompanyData, wacc: float = 0.115, terminal_growth: float = 0.05,
                   exit_multiple: float | None = None) -> DCFInputs:
    """Starting assumptions derived from reported history. Meant to be edited."""
    rev = cd.revenue
    if len(rev) >= 2 and rev[0] > 0:
        cagr = (rev[-1] / rev[0]) ** (1 / (len(rev) - 1)) - 1
    else:
        cagr = 0.08
    g1 = min(max(cagr, 0.05), 0.16)
    g5 = max(min(g1, 0.08), terminal_growth + 0.01)
    growth = list(np.linspace(g1, g5, N_YEARS))
    margin_last = cd.ltm_ebitda / cd.ltm_revenue
    margin = [margin_last] * N_YEARS

    def ratio(a, b, default):
        if a and b and len(a) and len(b) and b[-1]:
            return abs(a[-1]) / b[-1]
        return default

    da_pct = ratio(cd.da, cd.revenue, 0.03)
    capex_pct = ratio(cd.capex, cd.revenue, 0.04)
    nwc_pct = (cd.nwc / cd.ltm_revenue) if (cd.nwc is not None and cd.ltm_revenue) else 0.12
    nwc_pct = min(max(nwc_pct, 0.0), 0.40)
    if exit_multiple is None:
        ev = cd.enterprise_value
        exit_multiple = ev / cd.ltm_ebitda if ev and cd.ltm_ebitda else 12.0
    return DCFInputs(
        base_revenue=cd.ltm_revenue, growth=[float(x) for x in growth],
        ebitda_margin=[float(m) for m in margin], da_pct=float(da_pct),
        capex_pct=float(capex_pct), nwc_pct_incr=float(nwc_pct), tax_rate=float(cd.tax_rate),
        wacc=wacc, terminal_growth=terminal_growth, exit_multiple=float(exit_multiple),
        net_debt=float(cd.net_debt or 0.0), shares=float(cd.shares_cr),
    )
