"""Football-field ranges (INR per share) combining every valuation method."""
from __future__ import annotations

from dataclasses import replace
from typing import List, Optional

import numpy as np

from .dcf import DCFInputs, run_dcf
from .lbo import LBOInputs, solve_entry_multiple
from .models import CompanyData


def _grid_range(fn, axis_a, axis_b) -> tuple[float, float]:
    vals = [fn(a, b) for a in axis_a for b in axis_b]
    vals = [v for v in vals if v == v]
    return (min(vals), max(vals)) if vals else (float("nan"), float("nan"))


def build_football(target: CompanyData, implied: dict, dcf_in: DCFInputs,
                   lbo_in: Optional[LBOInputs], irr_low: float = 0.20,
                   irr_high: float = 0.25) -> List[dict]:
    rows: List[dict] = []
    if target.week52_low and target.week52_high:
        rows.append({"method": "52-week trading range", "low": target.week52_low,
                     "high": target.week52_high})
    if "EV/EBITDA" in implied:
        rows.append({"method": "Comps: EV/EBITDA (Q1-Q3)", "low": implied["EV/EBITDA"]["Q1"],
                     "high": implied["EV/EBITDA"]["Q3"]})
    if "P/E" in implied:
        rows.append({"method": "Comps: P/E (Q1-Q3)", "low": implied["P/E"]["Q1"],
                     "high": implied["P/E"]["Q3"]})

    waccs = [dcf_in.wacc + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    gs = [dcf_in.terminal_growth + d for d in (-0.005, 0, 0.005)]
    lo, hi = _grid_range(lambda w, g: run_dcf(replace(dcf_in, wacc=w, terminal_growth=g))["price_gordon"],
                         waccs, gs)
    rows.append({"method": "DCF: Gordon growth (WACC +/-1%, g +/-0.5%)", "low": lo, "high": hi})
    mults = [dcf_in.exit_multiple + d for d in (-2, 0, 2)]
    lo, hi = _grid_range(lambda w, m: run_dcf(replace(dcf_in, wacc=w, exit_multiple=m))["price_exit"],
                         waccs, mults)
    rows.append({"method": "DCF: exit multiple (WACC +/-1%, exit +/-2x)", "low": lo, "high": hi})

    if lbo_in is not None:
        nd = dcf_in.net_debt
        m_hi = solve_entry_multiple(lbo_in, irr_low)
        m_lo = solve_entry_multiple(lbo_in, irr_high)
        if m_hi is not None and m_lo is not None:
            f = lambda m: (m * lbo_in.ebitda0 - nd) / dcf_in.shares
            rows.append({"method": f"LBO ability to pay ({irr_high:.0%} to {irr_low:.0%} IRR)",
                         "low": f(m_lo), "high": f(m_hi)})
    for r in rows:
        r["mid"] = (r["low"] + r["high"]) / 2
    return rows
