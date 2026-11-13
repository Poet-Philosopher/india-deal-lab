"""Leveraged buyout model.

Mechanics (kept deliberately simple and fully auditable)
--------------------------------------------------------
* Cash-free / debt-free purchase: Uses = Entry EV + fees + minimum cash funded.
* Sources = senior debt + mezzanine + sponsor equity (equity is the plug).
* Interest is charged on opening balances, so there is no circularity.
* Mezzanine pays cash interest and accrues PIK interest onto its balance.
* Cash taxes = max(0, (EBIT - total interest incl. PIK) x tax rate).
* Mandatory senior amortisation = amort_pct x original senior debt (capped at balance).
* Cash sweep = sweep_pct x free cash after mandatory amortisation, capped at balance.
* No interim dividends; IRR = MOIC^(1/hold) - 1.
* Operating case (revenue growth, margins, capex, NWC) is supplied by the same drivers as the DCF.

Returns attribution (sums exactly to the equity gain):
  EBITDA growth + multiple expansion + net-debt paydown - transaction fees.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional

import numpy as np
import pandas as pd

from .dcf import operating_projection


@dataclass
class LBOInputs:
    revenue0: float
    ebitda0: float
    growth: List[float]
    ebitda_margin: List[float]
    da_pct: float
    capex_pct: float
    nwc_pct_incr: float
    tax_rate: float
    entry_multiple: float
    senior_x: float
    mezz_x: float
    senior_rate: float
    mezz_cash_rate: float
    mezz_pik_rate: float
    fee_pct: float
    min_cash: float
    amort_pct: float
    sweep_pct: float
    exit_multiple: float
    hold_years: int = 5


def run_lbo(i: LBOInputs) -> dict:
    n = int(i.hold_years)
    assert 1 <= n <= len(i.growth), "hold_years must fit inside the projection horizon"

    ev0 = i.entry_multiple * i.ebitda0
    fees = i.fee_pct * ev0
    senior0 = i.senior_x * i.ebitda0
    mezz0 = i.mezz_x * i.ebitda0
    uses = ev0 + fees + i.min_cash
    equity0 = uses - senior0 - mezz0

    p = operating_projection(i.revenue0, i.growth[:n], i.ebitda_margin[:n], i.da_pct,
                             i.capex_pct, i.nwc_pct_incr, i.tax_rate)
    senior_beg, senior_end, mezz_beg, mezz_end = [], [], [], []
    sen_int, mez_cash, mez_pik, taxes, cfads, mand, sweep = ([] for _ in range(7))
    cash_end = []
    s, m, c = senior0, mezz0, i.min_cash
    for t in range(n):
        senior_beg.append(s); mezz_beg.append(m)
        si = s * i.senior_rate
        mc = m * i.mezz_cash_rate
        mp = m * i.mezz_pik_rate
        tax = max(0.0, (p["ebit"][t] - si - mc - mp) * i.tax_rate)
        cf = p["ebitda"][t] - tax - p["capex"][t] - p["dnwc"][t] - si - mc
        md = min(s, i.amort_pct * senior0)
        sw = min(s - md, i.sweep_pct * max(0.0, cf - md))
        s = s - md - sw
        m = m + mp
        c = c + cf - md - sw
        sen_int.append(si); mez_cash.append(mc); mez_pik.append(mp); taxes.append(tax)
        cfads.append(cf); mand.append(md); sweep.append(sw)
        senior_end.append(s); mezz_end.append(m); cash_end.append(c)

    ebitda_n = p["ebitda"][-1]
    ev_exit = i.exit_multiple * ebitda_n
    net_debt_exit = senior_end[-1] + mezz_end[-1] - cash_end[-1]
    equity_exit = ev_exit - net_debt_exit
    moic = equity_exit / equity0 if equity0 > 0 else float("nan")
    irr = (moic ** (1 / n) - 1) if (equity0 > 0 and moic > 0) else float("nan")

    net_debt_entry = senior0 + mezz0 - i.min_cash
    attribution = {
        "EBITDA growth": i.entry_multiple * (ebitda_n - i.ebitda0),
        "Multiple expansion": (i.exit_multiple - i.entry_multiple) * ebitda_n,
        "Net debt paydown": net_debt_entry - net_debt_exit,
        "Transaction fees": -fees,
    }
    return {
        "entry_ev": ev0, "fees": fees, "uses": uses,
        "sources": {"Senior debt": senior0, "Mezzanine": mezz0, "Sponsor equity": equity0},
        "equity0": equity0, "projection": p,
        "senior_beg": senior_beg, "senior_end": senior_end,
        "mezz_beg": mezz_beg, "mezz_end": mezz_end, "cash_end": cash_end,
        "senior_interest": sen_int, "mezz_cash_interest": mez_cash, "mezz_pik": mez_pik,
        "taxes": taxes, "cash_flow_pre_repayment": cfads, "mandatory": mand, "sweep": sweep,
        "ebitda_exit": ebitda_n, "ev_exit": ev_exit, "net_debt_exit": net_debt_exit,
        "equity_exit": equity_exit, "moic": moic, "irr": irr,
        "equity_gain": equity_exit - equity0, "attribution": attribution,
        "leverage_entry": (senior0 + mezz0) / i.ebitda0,
        "leverage_exit": (senior_end[-1] + mezz_end[-1]) / ebitda_n,
        "interest_cover_y1": p["ebitda"][0] / max(sen_int[0] + mez_cash[0], 1e-9),
        "min_cash_balance": min(cash_end),
        "cash_shortfall": min(cash_end) < 0,
    }


def _irr_at(i: LBOInputs, **kw) -> float:
    r = run_lbo(replace(i, **kw))["irr"]
    return r if r == r else float("inf")  # non-positive equity -> treat as unbounded return


def solve_entry_multiple(i: LBOInputs, target_irr: float) -> Optional[float]:
    """Highest entry multiple that still delivers target_irr (leverage fixed in x EBITDA)."""
    lo = max(1.0, i.senior_x + i.mezz_x + 0.25)
    hi = 60.0
    if _irr_at(i, entry_multiple=lo) < target_irr:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if _irr_at(i, entry_multiple=mid) >= target_irr:
            lo = mid
        else:
            hi = mid
    return lo


def solve_exit_multiple(i: LBOInputs, target_irr: float) -> Optional[float]:
    """Lowest exit multiple that delivers target_irr at the current entry price."""
    lo, hi = 1.0, 80.0
    if _irr_at(i, exit_multiple=hi) < target_irr:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if _irr_at(i, exit_multiple=mid) >= target_irr:
            hi = mid
        else:
            lo = mid
    return hi


def irr_grid(i: LBOInputs, entry_mults, exit_mults) -> pd.DataFrame:
    data = [[run_lbo(replace(i, entry_multiple=e, exit_multiple=x))["irr"] for x in exit_mults]
            for e in entry_mults]
    return pd.DataFrame(data, index=[f"{e:.1f}x" for e in entry_mults],
                        columns=[f"{x:.1f}x" for x in exit_mults])
