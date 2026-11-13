"""India Deal Lab: Streamlit front end."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from deal_lab import __version__
from deal_lab.comps import comps_table, flag_outliers, implied_valuation, summary_stats
from deal_lab.data import SAMPLE_PRESET, get_company
from deal_lab.dcf import (N_YEARS, DCFInputs, compute_wacc, default_inputs, run_dcf,
                          sensitivity_wacc_exit, sensitivity_wacc_g)
from deal_lab.excel_export import build_workbook
from deal_lab.football import build_football
from deal_lab.lbo import LBOInputs, irr_grid, run_lbo, solve_entry_multiple, solve_exit_multiple
from deal_lab.memo import build_memo
from deal_lab.models import CompanyData
from deal_lab.universe import DEFAULT_PRESET, PRESETS

st.set_page_config(page_title="India Deal Lab | Valuation and LBO analysis", layout="wide",
                   initial_sidebar_state="expanded")

PALETTE = {"navy": "#1f3a5f", "steel": "#5b7a99", "grey": "#8a94a0", "line": "#d5dae1",
           "pos": "#2e6b4f", "neg": "#9b3d3d"}

st.markdown("""
<style>
html, body, [class*="st-"] { font-feature-settings: "tnum" 1, "lnum" 1; }
.block-container { padding-top: 2.2rem; max-width: 1280px; }
h1 { font-weight: 600; letter-spacing: -0.01em; font-size: 1.9rem; }
h2, h3 { font-weight: 600; letter-spacing: -0.005em; }
[data-testid="stMetric"] { background: #f6f7f9; border: 1px solid #e1e5ea; border-radius: 4px;
                           padding: 0.7rem 0.9rem; }
[data-testid="stMetricLabel"] p { font-size: 0.8rem; color: #4a5563; }
[data-testid="stMetricValue"] { font-size: 1.35rem; font-weight: 600; }
.stTabs [data-baseweb="tab-list"] { gap: 0.25rem; border-bottom: 1px solid #d5dae1; }
.stTabs [data-baseweb="tab"] { padding: 0.5rem 1rem; }
footer, #MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


def style_fig(fig, height=None):
    fig.update_layout(template="simple_white", font={"family": "Inter, Segoe UI, Arial, sans-serif",
                      "size": 13, "color": "#1b2430"}, margin={"l": 10, "r": 10, "t": 50, "b": 10},
                      **({"height": height} if height else {}))
    return fig

MODES = {
    "Auto (live, then bundled snapshot)": "auto",
    "Live only (Yahoo Finance)": "live",
    "Bundled snapshot only": "snapshot",
    "Sample (synthetic demo data)": "sample",
}


def fmt_cr(x) -> str:
    return "n/a" if x is None or x != x else f"Rs {x:,.0f} cr"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _load(ticker: str, mode: str) -> dict:
    return get_company(ticker, mode).to_dict()


def load(ticker: str, mode: str) -> CompanyData:
    return CompanyData.from_dict(_load(ticker, mode))


# ------------------------------------------------------------------ sidebar
st.sidebar.title("India Deal Lab")
st.sidebar.caption(f"Version {__version__}. Valuation, LBO and investment memo.")
mode_label = st.sidebar.radio("Data source", list(MODES), index=0)
mode = MODES[mode_label]

if mode == "sample":
    cfg = SAMPLE_PRESET
    st.sidebar.selectbox("Case study", ["Sample Co A (synthetic)"], disabled=True)
    peers_default = cfg["peers"]
    note = "Synthetic companies for demonstration only."
else:
    preset_name = st.sidebar.selectbox("Case study", list(PRESETS), index=list(PRESETS).index(DEFAULT_PRESET))
    cfg = PRESETS[preset_name]
    peers_default = cfg["peers"]
    note = cfg["note"]
st.sidebar.caption(note)

hurdle = st.sidebar.slider("Sponsor hurdle IRR", 0.10, 0.35, 0.20, 0.01, format="%.2f")

st.title("India Deal Lab")
st.caption("Trading comparables, DCF, leveraged buyout, football field and investment committee memo "
           "for NSE-listed companies. For educational use only; not investment advice.")

try:
    with st.spinner("Loading company data..."):
        target = load(cfg["ticker"], mode)
except Exception as exc:
    st.error(str(exc))
    st.info("Select **Sample (synthetic demo data)** in the sidebar, or generate bundled snapshots by running "
            "`python scripts/refresh_snapshots.py` (or the Refresh data snapshots workflow on GitHub).")
    st.stop()

if target.source == "sample":
    st.warning("Synthetic sample data. The companies and figures are illustrative and not real.")
elif target.source == "snapshot":
    st.info(f"Showing bundled snapshot dated {target.as_of} (live Yahoo Finance data was unavailable).")

peer_objs: list[CompanyData] = []
failed: list[str] = []
with st.spinner("Loading peers..."):
    for t in peers_default:
        try:
            p = load(t, mode)
            (peer_objs if p.is_complete() else failed).append(p if p.is_complete() else t)
        except Exception:
            failed.append(t)
if failed:
    st.warning("Peers skipped (incomplete or unavailable data): " + ", ".join(failed))

# ---- manual overrides ---------------------------------------------------
with st.sidebar.expander("Override company inputs"):
    price = st.number_input("Share price (Rs)", value=float(target.price), min_value=0.01)
    shares = st.number_input("Shares (crore)", value=float(target.shares_cr), min_value=0.0001,
                             format="%.4f")
    rev0 = st.number_input("LTM revenue (Rs cr)", value=float(target.ltm_revenue), min_value=1.0)
    ebitda0 = st.number_input("LTM EBITDA (Rs cr)", value=float(target.ltm_ebitda), min_value=1.0)
    debt = st.number_input("Total debt (Rs cr)", value=float(target.total_debt), min_value=0.0)
    cash = st.number_input("Cash (Rs cr)", value=float(target.cash), min_value=0.0)

t = replace(target, price=price, shares_cr=shares, market_cap=price * shares,
            total_debt=debt, cash=cash,
            revenue=[*target.revenue[:-1], rev0], ebitda=[*target.ebitda[:-1], ebitda0])

# ---- comps (computed once, reused by every tab) ------------------------------
comp_df = comps_table(peer_objs) if peer_objs else pd.DataFrame()
exclude: list[str] = []
tabs = st.tabs(["Overview", "Comps", "DCF", "LBO", "Football field", "IC memo", "Excel"])

# ===================================================================== overview
with tabs[0]:
    st.subheader(f"{t.name} ({t.ticker})")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", f"Rs {t.price:,.1f}")
    c2.metric("Market cap", fmt_cr(t.market_cap))
    c3.metric("Net debt", fmt_cr(t.net_debt))
    c4.metric("EV / LTM EBITDA", f"{t.enterprise_value / t.ltm_ebitda:.1f}x")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("LTM revenue", fmt_cr(t.ltm_revenue))
    c2.metric("LTM EBITDA", fmt_cr(t.ltm_ebitda))
    c3.metric("EBITDA margin", f"{t.ltm_ebitda / t.ltm_revenue:.1%}")
    c4.metric("Data as of", t.as_of or "n/a")
    if t.summary:
        st.write(t.summary)
    if t.revenue and len(t.ebitda) >= len(t.revenue):
        n_h = len(t.revenue)
        yrs_h = t.years[-n_h:] if len(t.years) >= n_h else [f"Year {i + 1}" for i in range(n_h)]
        hf = go.Figure([go.Bar(name="Revenue", x=yrs_h, y=t.revenue, marker_color=PALETTE["navy"]),
                        go.Bar(name="EBITDA", x=yrs_h, y=t.ebitda[-n_h:], marker_color=PALETTE["steel"])])
        hf.update_layout(barmode="group", title="Revenue and EBITDA history (Rs crore)",
                         xaxis={"type": "category"}, legend={"orientation": "h", "y": -0.15})
        st.plotly_chart(style_fig(hf, 340), width="stretch")
    if t.warnings:
        with st.expander(f"Data quality notes ({len(t.warnings)})"):
            for w in t.warnings:
                st.write("- " + w)

# ======================================================================= comps
with tabs[1]:
    st.subheader("Trading comparables")
    if comp_df.empty or len(comp_df) < 2:
        st.warning("Not enough complete peers to build comps.")
        stats = None
        implied = {}
    else:
        flags = flag_outliers(comp_df["EV/EBITDA"])
        out_tickers = list(comp_df.loc[flags, "Ticker"])
        exclude = st.multiselect("Exclude peers from statistics", list(comp_df["Ticker"]),
                                 default=out_tickers,
                                 help="Peers outside 1.5 x IQR on EV/EBITDA are pre-selected.")
        show = comp_df.copy()
        show["Outlier"] = flags.map({True: "yes", False: ""})
        st.dataframe(show.style.format({
            "Mkt cap (Rs cr)": "{:,.0f}", "EV (Rs cr)": "{:,.0f}", "EBITDA margin %": "{:.1f}",
            "EV/EBITDA": "{:.1f}x", "EV/Sales": "{:.2f}x", "P/E": "{:.1f}x"}), hide_index=True,
            width="stretch")
        stats = summary_stats(comp_df, exclude)
        st.dataframe(stats.style.format("{:.1f}"), width="stretch")
        implied = implied_valuation(t, stats)
        if implied:
            rows = [{"Multiple": k, "Q1": v["Q1"], "Median": v["Median"], "Q3": v["Q3"]}
                    for k, v in implied.items()]
            st.markdown("**Implied value per share (Rs)**")
            st.dataframe(pd.DataFrame(rows).style.format({"Q1": "{:,.0f}", "Median": "{:,.0f}",
                                                          "Q3": "{:,.0f}"}), hide_index=True)

# ========================================================================= dcf
with tabs[2]:
    st.subheader("Discounted cash flow")
    base = default_inputs(t)
    left, right = st.columns(2)
    with left:
        st.markdown("**Operating case**")
        g1 = st.slider("Revenue growth, year 1", 0.0, 0.25, float(round(base.growth[0], 3)), 0.005,
                       format="%.3f")
        g5 = st.slider("Revenue growth, year 5", 0.0, 0.20, float(round(base.growth[-1], 3)), 0.005,
                       format="%.3f")
        m_now = min(max(t.ltm_ebitda / t.ltm_revenue, 0.02), 0.45)
        m1 = st.slider("EBITDA margin, year 1", 0.02, 0.45, float(round(m_now, 3)), 0.005, format="%.3f")
        m5 = st.slider("EBITDA margin, year 5", 0.02, 0.45, float(round(m_now, 3)), 0.005, format="%.3f")
        da_pct = st.slider("D&A % of revenue", 0.0, 0.12,
                           float(round(min(base.da_pct, 0.12), 3)), 0.0025, format="%.4f")
        capex_pct = st.slider("Capex % of revenue", 0.0, 0.15,
                              float(round(min(base.capex_pct, 0.15), 3)), 0.0025, format="%.4f")
        nwc_pct = st.slider("NWC % of incremental revenue", 0.0, 0.40, float(round(base.nwc_pct_incr, 3)),
                            0.01, format="%.2f")
        tax = st.slider("Tax rate", 0.10, 0.35, float(round(t.tax_rate, 3)), 0.005, format="%.3f")
    with right:
        st.markdown("**Discount rate** (placeholders: update the risk-free rate and ERP before use)")
        rf = st.number_input("Risk-free rate (India 10Y G-Sec)", value=0.068, step=0.001, format="%.3f")
        erp = st.number_input("Equity risk premium", value=0.065, step=0.005, format="%.3f")
        beta = st.number_input("Beta", value=float(t.beta if t.beta else 1.0), step=0.05, format="%.2f")
        size = st.number_input("Size premium", value=0.0, step=0.005, format="%.3f")
        kd = st.number_input("Pre-tax cost of debt", value=0.09, step=0.005, format="%.3f")
        dw = st.slider("Target debt weight", 0.0, 0.6, 0.10, 0.05)
        w = compute_wacc(rf, erp, beta, size, kd, tax, dw)
        st.metric("WACC", f"{w['wacc']:.2%}",
                  help=f"Cost of equity {w['cost_of_equity']:.2%}; after-tax cost of debt "
                       f"{w['after_tax_cost_of_debt']:.2%}")
        tg = st.slider("Terminal growth", 0.02, 0.07, 0.05, 0.0025, format="%.4f")
        mkt_mult = t.enterprise_value / t.ltm_ebitda
        exit_mult = st.slider("Exit EV/EBITDA", 4.0, 45.0, float(round(min(max(mkt_mult, 4.0), 45.0), 1)), 0.5)
        mid = st.checkbox("Mid-year convention", value=False)

    growth = list(np.linspace(g1, g5, N_YEARS))
    margin = list(np.linspace(m1, m5, N_YEARS))
    dcf_in = DCFInputs(base_revenue=t.ltm_revenue, growth=growth, ebitda_margin=margin, da_pct=da_pct,
                       capex_pct=capex_pct, nwc_pct_incr=nwc_pct, tax_rate=tax, wacc=w["wacc"],
                       terminal_growth=tg, exit_multiple=exit_mult, net_debt=float(t.net_debt),
                       shares=t.shares_cr, mid_year=mid)
    dcf = run_dcf(dcf_in)
    if w["wacc"] <= tg:
        st.error("WACC is at or below terminal growth, so the Gordon growth value is undefined. "
                 "Lower the terminal growth rate or raise the discount rate.")

    a, b_, c = st.columns(3)
    a.metric("Value / share (Gordon)", f"Rs {dcf['price_gordon']:,.0f}",
             f"{dcf['price_gordon'] / t.price - 1:+.0%} vs price")
    b_.metric("Value / share (exit multiple)", f"Rs {dcf['price_exit']:,.0f}",
              f"{dcf['price_exit'] / t.price - 1:+.0%} vs price")
    c.metric("Blended", f"Rs {dcf['price_blended']:,.0f}", f"{dcf['price_blended'] / t.price - 1:+.0%}")
    st.caption(f"Terminal value share of EV: {dcf['tv_share_gordon']:.0%} (Gordon), "
               f"{dcf['tv_share_exit']:.0%} (exit). Gordon implies a {dcf['implied_exit_multiple_from_gordon']:.1f}x "
               f"exit multiple; the exit multiple implies {dcf['implied_growth_from_exit']:.1%} terminal growth.")
    p = dcf["projection"]
    proj = pd.DataFrame({"Revenue": p["revenue"], "EBITDA": p["ebitda"], "EBIT": p["ebit"],
                         "NOPAT": p["nopat"], "Capex": p["capex"], "Increase in NWC": p["dnwc"],
                         "FCFF": p["fcff"], "PV of FCFF": dcf["pv_fcff"]},
                        index=[f"Year {i + 1}" for i in range(N_YEARS)]).T
    st.dataframe(proj.style.format("{:,.0f}"), width="stretch")
    waccs = [dcf_in.wacc + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    s1, s2 = st.columns(2)
    s1.markdown("**Value per share: WACC vs terminal growth**")
    s1.dataframe(sensitivity_wacc_g(dcf_in, waccs, [tg - 0.01, tg - 0.005, tg, tg + 0.005, tg + 0.01])
                 .style.format("{:,.0f}"))
    s2.markdown("**Value per share: WACC vs exit multiple**")
    s2.dataframe(sensitivity_wacc_exit(dcf_in, waccs, [exit_mult + d for d in (-4, -2, 0, 2, 4)])
                 .style.format("{:,.0f}"))

# ========================================================================= lbo
with tabs[3]:
    st.subheader("Leveraged buyout")
    l1, l2 = st.columns(2)
    with l1:
        premium = st.slider("Control premium to current price", 0.0, 0.70, 0.25, 0.05, format="%.2f")
        entry_price = t.price * (1 + premium)
        entry_ev = entry_price * t.shares_cr + t.net_debt
        entry_mult = entry_ev / t.ltm_ebitda
        st.metric("Offer price", f"Rs {entry_price:,.0f}", f"Entry {entry_mult:.1f}x LTM EBITDA", delta_color="off")
        senior_x = st.slider("Senior debt (x EBITDA)", 0.0, 6.0, 3.0, 0.25)
        mezz_x = st.slider("Mezzanine (x EBITDA)", 0.0, 3.0, 1.0, 0.25)
        hold = st.slider("Hold period (years)", 3, 5, 5)
    with l2:
        senior_rate = st.slider("Senior interest rate", 0.06, 0.16, 0.105, 0.0025, format="%.4f")
        mezz_cash = st.slider("Mezzanine cash rate", 0.06, 0.18, 0.11, 0.0025, format="%.4f")
        mezz_pik = st.slider("Mezzanine PIK rate", 0.0, 0.08, 0.03, 0.005, format="%.3f")
        fee_pct = st.slider("Transaction fees (% of EV)", 0.0, 0.05, 0.02, 0.005, format="%.3f")
        amort = st.slider("Mandatory amortisation (% of senior)", 0.0, 0.20, 0.05, 0.01, format="%.2f")
        sweep = st.slider("Cash sweep", 0.0, 1.0, 0.75, 0.05, format="%.2f")
        same_exit = st.checkbox("Exit multiple = entry multiple", value=True)
        exit_m = entry_mult if same_exit else st.slider("Exit EV/EBITDA", 4.0, 45.0,
                                                          float(round(min(max(entry_mult, 4.0), 45.0), 1)), 0.5)

    lbo_in = LBOInputs(revenue0=t.ltm_revenue, ebitda0=t.ltm_ebitda, growth=growth, ebitda_margin=margin,
                       da_pct=da_pct, capex_pct=capex_pct, nwc_pct_incr=nwc_pct, tax_rate=tax,
                       entry_multiple=entry_mult, senior_x=senior_x, mezz_x=mezz_x,
                       senior_rate=senior_rate, mezz_cash_rate=mezz_cash, mezz_pik_rate=mezz_pik,
                       fee_pct=fee_pct, min_cash=0.01 * t.ltm_revenue, amort_pct=amort,
                       sweep_pct=sweep, exit_multiple=exit_m, hold_years=hold)
    lbo = run_lbo(lbo_in)

    if lbo["sources"]["Sponsor equity"] <= 0:
        st.error("Debt exceeds total uses; reduce leverage.")
    irr_txt = f"{lbo['irr']:.1%}" if lbo["irr"] == lbo["irr"] else "n/a"
    m1_, m2_, m3_, m4_ = st.columns(4)
    m1_.metric("IRR", irr_txt, "meets hurdle" if lbo["irr"] == lbo["irr"] and lbo["irr"] >= hurdle else "below hurdle")
    m2_.metric("MOIC", f"{lbo['moic']:.2f}x")
    m3_.metric("Leverage in / out", f"{lbo['leverage_entry']:.1f}x / {lbo['leverage_exit']:.1f}x")
    m4_.metric("Year-1 interest cover", f"{lbo['interest_cover_y1']:.1f}x")
    if lbo["cash_shortfall"]:
        st.warning("Cash falls below zero in at least one year: debt service is not covered. "
                   "Lower leverage or a revolver would be needed.")

    su1, su2 = st.columns(2)
    su1.markdown("**Sources**")
    su1.dataframe(pd.DataFrame({"Rs cr": lbo["sources"]}).style.format("{:,.0f}"))
    su2.markdown("**Uses**")
    su2.dataframe(pd.DataFrame({"Rs cr": {"Enterprise value": lbo["entry_ev"], "Fees": lbo["fees"],
                                          "Minimum cash": lbo_in.min_cash,
                                          "Total": lbo["uses"]}}).style.format("{:,.0f}"))

    yrs = [f"Year {i + 1}" for i in range(hold)]
    sched = pd.DataFrame({"EBITDA": lbo["projection"]["ebitda"], "Senior interest": lbo["senior_interest"],
                          "Mezz cash interest": lbo["mezz_cash_interest"], "Cash taxes": lbo["taxes"],
                          "Cash flow pre-repayment": lbo["cash_flow_pre_repayment"],
                          "Mandatory repayment": lbo["mandatory"], "Cash sweep": lbo["sweep"],
                          "Senior debt (end)": lbo["senior_end"], "Mezzanine (end)": lbo["mezz_end"],
                          "Cash (end)": lbo["cash_end"]}, index=yrs).T
    st.markdown("**Debt schedule**")
    st.dataframe(sched.style.format("{:,.0f}"), width="stretch")

    attr = lbo["attribution"]
    fig = go.Figure(go.Waterfall(
        x=[*attr.keys(), "Equity gain"], measure=["relative"] * len(attr) + ["total"],
        y=[*attr.values(), 0], text=[f"{v:,.0f}" for v in [*attr.values(), lbo["equity_gain"]]],
        connector={"line": {"color": PALETTE["grey"]}},
        increasing={"marker": {"color": PALETTE["pos"]}}, decreasing={"marker": {"color": PALETTE["neg"]}},
        totals={"marker": {"color": PALETTE["navy"]}}))
    fig.update_layout(title="Returns attribution (Rs crore)", showlegend=False)
    style_fig(fig, 380)
    st.plotly_chart(fig, width="stretch")

    st.markdown("**IRR sensitivity: entry multiple vs exit multiple**")
    ems = [entry_mult + d for d in (-2, -1, 0, 1, 2)]
    xms = [exit_m + d for d in (-2, -1, 0, 1, 2)]
    grid = irr_grid(lbo_in, ems, xms)
    st.dataframe(grid.style.format("{:.1%}").background_gradient(cmap="Blues", axis=None))

    st.markdown(f"**What must be true for a {hurdle:.0%} IRR**")
    max_entry = solve_entry_multiple(lbo_in, hurdle)
    min_exit = solve_exit_multiple(lbo_in, hurdle)
    w1, w2 = st.columns(2)
    if max_entry:
        mp = (max_entry * t.ltm_ebitda - t.net_debt) / t.shares_cr
        w1.metric("Max entry multiple", f"{max_entry:.1f}x", f"Rs {mp:,.0f}/share ({mp / t.price - 1:+.0%})")
    else:
        w1.metric("Max entry multiple", "none", "target unreachable at these terms")
    if min_exit:
        w2.metric("Min exit multiple at this entry price", f"{min_exit:.1f}x",
                  f"{min_exit - entry_mult:+.1f}x vs entry")
    else:
        w2.metric("Min exit multiple", "none", "target unreachable")

# ===================================================================== football
with tabs[4]:
    st.subheader("Football field (Rs per share)")
    football = build_football(t, implied, dcf_in, lbo_in, irr_low=hurdle, irr_high=hurdle + 0.05)
    ff = go.Figure()
    for r in football:
        ff.add_trace(go.Bar(y=[r["method"]], x=[r["high"] - r["low"]], base=[r["low"]],
                            orientation="h", showlegend=False, marker_color=PALETTE["navy"],
                            text=f"{r['low']:,.0f} to {r['high']:,.0f}", textposition="inside",
                            hovertemplate=f"{r['method']}<br>Rs %{{base:,.0f}} to Rs {r['high']:,.0f}<extra></extra>"))
    ff.add_vline(x=t.price, line_dash="dash", line_color=PALETTE["neg"],
                 annotation_text=f"Price Rs {t.price:,.0f}", annotation_position="top")
    ff.add_vline(x=entry_price, line_dash="dot", line_color=PALETTE["pos"],
                 annotation_text=f"Offer Rs {entry_price:,.0f}", annotation_position="bottom")
    ff.update_layout(xaxis_title="Rs per share", yaxis={"autorange": "reversed"})
    style_fig(ff, 120 + 70 * len(football))
    st.plotly_chart(ff, width="stretch")
    st.dataframe(pd.DataFrame(football).rename(columns={"method": "Method", "low": "Low", "high": "High",
                                                        "mid": "Mid"})
                 .style.format({"Low": "{:,.0f}", "High": "{:,.0f}", "Mid": "{:,.0f}"}), hide_index=True)

# ======================================================================== memo
with tabs[5]:
    st.subheader("Investment committee memo")
    stats_for_memo = stats if comp_df is not None and not comp_df.empty and len(comp_df) >= 2 else None
    memo_md = build_memo(t, peer_objs, stats_for_memo, implied, dcf_in, dcf, lbo_in, lbo, football,
                         premium, hurdle, max_entry)
    st.markdown(memo_md)
    st.download_button("Download memo (.md)", memo_md, file_name=f"IC_memo_{t.ticker}.md",
                       mime="text/markdown")

# ======================================================================= excel
with tabs[6]:
    st.subheader("Excel export")
    st.write("A formula-live workbook (Assumptions, DCF, LBO). Change a blue input and the model "
             "recalculates in Excel. It mirrors the Python model; the Excel LBO uses a fixed "
             "5-year horizon with the exit year taken from the hold period.")
    blob = build_workbook(t, dcf_in, lbo_in, t.price)
    st.download_button("Download model (.xlsx)", blob, file_name=f"DealLab_{t.ticker}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


st.divider()
st.caption("India Deal Lab is an educational project. Data is sourced from Yahoo Finance via yfinance or from "
           "bundled snapshots and may be incomplete or restated. Nothing here constitutes investment advice.")
