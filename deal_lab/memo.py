"""Investment committee memo, assembled only from model outputs.

Every number comes from the arguments; nothing is typed by hand. The recommendation is a
rule-based, model-implied stance and is explicitly not investment advice.
"""
from __future__ import annotations

from typing import List, Optional

from .dcf import DCFInputs
from .lbo import LBOInputs
from .models import CompanyData


def _cr(x) -> str:
    return f"Rs {x:,.0f} cr"


def _px(x) -> str:
    return f"Rs {x:,.0f}"


def _pct(x) -> str:
    return f"{x:.1%}"


def build_memo(target: CompanyData, peers: List[CompanyData], mult_stats, implied: dict,
               dcf_in: DCFInputs, dcf: dict, lbo_in: LBOInputs, lbo: dict,
               football: List[dict], premium: float, hurdle: float,
               max_entry_at_hurdle: Optional[float]) -> str:
    price = target.price
    ev_ebitda = target.enterprise_value / target.ltm_ebitda
    margin = target.ltm_ebitda / target.ltm_revenue
    blended = dcf["price_blended"]
    upside = blended / price - 1
    irr = lbo["irr"]
    meets = irr == irr and irr >= hurdle

    comps_mid = implied.get("EV/EBITDA", {}).get("Median")
    lines = []
    A = lines.append
    A(f"# Investment Committee Memo: {target.name} ({target.ticker})")
    A("")
    A(f"*Data source: {target.source}, as of {target.as_of}. Model-generated draft for learning and "
      "portfolio purposes. Not investment advice.*")
    if target.source == "sample":
        A("")
        A("> **Synthetic sample data. The company and every figure below are illustrative, not real.**")
    A("")
    A("## 1. Recommendation (model-implied)")
    if meets:
        stance = (f"**Proceed to next-stage diligence.** At a {_pct(premium)} premium "
                  f"({_px(price * (1 + premium))} per share, {lbo_in.entry_multiple:.1f}x LTM EBITDA) "
                  f"the base case returns {_pct(irr)} IRR / {lbo['moic']:.2f}x MOIC, above the "
                  f"{_pct(hurdle)} hurdle.")
    else:
        irr_txt = _pct(irr) if irr == irr else "n/a"
        stance = (f"**Pass at this price.** At a {_pct(premium)} premium "
                  f"({_px(price * (1 + premium))} per share, {lbo_in.entry_multiple:.1f}x LTM EBITDA) "
                  f"the base case returns {irr_txt} IRR / {lbo['moic']:.2f}x MOIC, below the "
                  f"{_pct(hurdle)} hurdle.")
    A(stance)
    if max_entry_at_hurdle:
        mx_price = (max_entry_at_hurdle * lbo_in.ebitda0 - dcf_in.net_debt) / dcf_in.shares
        A(f"The model supports paying up to about {max_entry_at_hurdle:.1f}x EBITDA "
          f"({_px(mx_price)} per share, {mx_price / price - 1:+.0%} vs market) to still clear the hurdle. "
          "A viable deal needs a price at or below that level.")
    else:
        A("No entry multiple clears the hurdle under the current leverage and operating assumptions.")
    A("")
    A("## 2. Business snapshot")
    A(f"- Sector / industry: {target.sector or 'n/a'} / {target.industry or 'n/a'}")
    A(f"- LTM revenue {_cr(target.ltm_revenue)}, EBITDA {_cr(target.ltm_ebitda)} "
      f"({_pct(margin)} margin), net income {_cr(target.ltm_net_income) if target.ltm_net_income else 'n/a'}")
    A(f"- Market cap {_cr(target.market_cap)}, net debt {_cr(target.net_debt)}, "
      f"EV {_cr(target.enterprise_value)} ({ev_ebitda:.1f}x LTM EBITDA)")
    if target.summary:
        A(f"- Company description (source summary): {target.summary}")
    A("")
    A("## 3. Valuation summary")
    A("| Method | Low (Rs/sh) | High (Rs/sh) | Midpoint |")
    A("|---|---|---|---|")
    for r in football:
        A(f"| {r['method']} | {r['low']:,.0f} | {r['high']:,.0f} | {r['mid']:,.0f} |")
    A("")
    A(f"- Current price {_px(price)}. DCF blended value {_px(blended)} ({upside:+.0%} vs price).")
    if comps_mid:
        A(f"- Peer-median EV/EBITDA (peer set of {len(peers)}) implies {_px(comps_mid)} per share "
          f"({comps_mid / price - 1:+.0%} vs price).")
    A(f"- WACC {_pct(dcf_in.wacc)}, terminal growth {_pct(dcf_in.terminal_growth)}, "
      f"exit multiple {dcf_in.exit_multiple:.1f}x. Terminal value is "
      f"{_pct(dcf['tv_share_gordon'])} of Gordon-growth EV.")
    A("")
    A("## 4. LBO returns")
    s = lbo["sources"]
    A(f"- Entry EV {_cr(lbo['entry_ev'])}; senior {_cr(s['Senior debt'])}, mezzanine "
      f"{_cr(s['Mezzanine'])}, sponsor equity {_cr(s['Sponsor equity'])} "
      f"({s['Sponsor equity'] / lbo['uses']:.0%} of uses).")
    A(f"- {lbo_in.hold_years}-year hold, exit at {lbo_in.exit_multiple:.1f}x: equity "
      f"{_cr(lbo['equity0'])} grows to {_cr(lbo['equity_exit'])} "
      f"({lbo['moic']:.2f}x MOIC, {_pct(irr) if irr == irr else 'n/a'} IRR).")
    attr = lbo["attribution"]
    A("- Value creation bridge: " + "; ".join(f"{k} {_cr(v)}" for k, v in attr.items()) + ".")
    A(f"- Leverage {lbo['leverage_entry']:.1f}x at entry falling to {lbo['leverage_exit']:.1f}x at exit; "
      f"year-1 interest cover {lbo['interest_cover_y1']:.1f}x.")
    A("")
    A("## 5. Key risks (generated from model sensitivities)")
    risks = []
    if dcf["tv_share_gordon"] == dcf["tv_share_gordon"] and dcf["tv_share_gordon"] > 0.7:
        risks.append(f"Valuation leans on terminal value ({_pct(dcf['tv_share_gordon'])} of DCF EV); "
                     "small changes in WACC or terminal growth move the answer materially.")
    if lbo["cash_shortfall"]:
        risks.append("Free cash flow does not cover debt service in at least one year: a revolver or "
                     "lower leverage would be required.")
    if lbo["interest_cover_y1"] < 2.5:
        risks.append(f"Thin year-1 interest cover ({lbo['interest_cover_y1']:.1f}x).")
    if lbo["attribution"]["Multiple expansion"] > 0.25 * max(lbo["equity_gain"], 1):
        risks.append("A large share of returns relies on multiple expansion at exit.")
    if lbo_in.exit_multiple >= lbo_in.entry_multiple:
        risks.append("Exit multiple is at or above the entry multiple; returns are sensitive to a "
                     "de-rating.")
    if target.warnings:
        risks.append("Data quality flags: " + " | ".join(target.warnings))
    if not risks:
        risks.append("No model-flagged red lines under the base case; diligence on margins, "
                     "financing availability and governance still required.")
    for r in risks:
        A(f"- {r}")
    A("- Indian acquisition-financing rules limit bank lending for share acquisitions, so the assumed "
      "senior/mezzanine structure is illustrative; real structures need legal and regulatory work.")
    A("")
    A("## 6. Key assumptions")
    A(f"- Revenue growth by year: {', '.join(_pct(g) for g in dcf_in.growth)}")
    A(f"- EBITDA margin by year: {', '.join(_pct(m) for m in dcf_in.ebitda_margin)}")
    A(f"- D&A {_pct(dcf_in.da_pct)} and capex {_pct(dcf_in.capex_pct)} of revenue; NWC "
      f"{_pct(dcf_in.nwc_pct_incr)} of incremental revenue; tax {_pct(dcf_in.tax_rate)}")
    A(f"- Debt: senior {lbo_in.senior_x:.1f}x at {_pct(lbo_in.senior_rate)}, mezzanine "
      f"{lbo_in.mezz_x:.1f}x at {_pct(lbo_in.mezz_cash_rate)} cash + {_pct(lbo_in.mezz_pik_rate)} PIK; "
      f"fees {_pct(lbo_in.fee_pct)} of EV; sweep {_pct(lbo_in.sweep_pct)}")
    A("")
    A("*Figures are in INR crore unless stated. Source data: Yahoo Finance via yfinance or a bundled "
      "snapshot; reported figures can be incomplete or restated.*")
    return "\n".join(lines)
