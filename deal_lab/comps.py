"""Trading comparables."""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np
import pandas as pd

from .models import CompanyData


def multiples(cd: CompanyData) -> dict:
    ev = cd.enterprise_value
    out = {"EV/EBITDA": np.nan, "EV/Sales": np.nan, "P/E": np.nan}
    if ev is not None and cd.ltm_ebitda and cd.ltm_ebitda > 0:
        out["EV/EBITDA"] = ev / cd.ltm_ebitda
    if ev is not None and cd.ltm_revenue and cd.ltm_revenue > 0:
        out["EV/Sales"] = ev / cd.ltm_revenue
    if cd.market_cap and cd.ltm_net_income and cd.ltm_net_income > 0:
        out["P/E"] = cd.market_cap / cd.ltm_net_income
    return out


def comps_table(peers: Iterable[CompanyData]) -> pd.DataFrame:
    rows = []
    for p in peers:
        m = multiples(p)
        rows.append({
            "Ticker": p.ticker, "Company": p.name,
            "Mkt cap (Rs cr)": p.market_cap, "EV (Rs cr)": p.enterprise_value,
            "EBITDA margin %": (p.ltm_ebitda / p.ltm_revenue * 100) if p.ltm_revenue else np.nan,
            **m,
        })
    return pd.DataFrame(rows)


def flag_outliers(series: pd.Series, k: float = 1.5) -> pd.Series:
    s = series.dropna()
    if len(s) < 4:
        return pd.Series(False, index=series.index)
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    return (series < lo) | (series > hi)


def summary_stats(df: pd.DataFrame, exclude: Optional[Iterable[str]] = None) -> pd.DataFrame:
    d = df[~df["Ticker"].isin(list(exclude or []))]
    stats = {}
    for col in ("EV/EBITDA", "EV/Sales", "P/E"):
        s = d[col].dropna()
        stats[col] = {
            "Count": len(s),
            "Min": s.min() if len(s) else np.nan,
            "Q1": s.quantile(0.25) if len(s) else np.nan,
            "Median": s.median() if len(s) else np.nan,
            "Mean": s.mean() if len(s) else np.nan,
            "Q3": s.quantile(0.75) if len(s) else np.nan,
            "Max": s.max() if len(s) else np.nan,
        }
    return pd.DataFrame(stats).T


def implied_valuation(target: CompanyData, stats: pd.DataFrame) -> dict:
    """Per-share ranges (Q1 - Median - Q3) implied for the target by each multiple."""
    nd = target.net_debt or 0.0
    sh = target.shares_cr
    res = {}
    def per_share_from_ev(ev):
        return (ev - nd) / sh
    for name, base, kind in (
        ("EV/EBITDA", target.ltm_ebitda, "ev"),
        ("EV/Sales", target.ltm_revenue, "ev"),
        ("P/E", target.ltm_net_income, "eq"),
    ):
        if base is None or base <= 0 or stats.loc[name, "Count"] < 2:
            continue
        pts = {}
        for q in ("Q1", "Median", "Q3"):
            m = stats.loc[name, q]
            val = m * base
            pts[q] = per_share_from_ev(val) if kind == "ev" else val / sh
        res[name] = pts
    return res
