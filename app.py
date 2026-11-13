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
           "pos": "#2a9d8f", "neg": "#c0504d", "warn": "#e9a23b", "teal_text": "#1f7a6f"}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
.stApp, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp label,
[data-testid="stMetric"], [data-testid="stSidebar"] { font-family: "Inter", "Segoe UI", Arial, sans-serif; }
html, body, [class*="st-"] { font-feature-settings: "tnum" 1, "lnum" 1; }
.block-container { padding-top: 2.2rem; max-width: 1280px; }
h1 { font-weight: 600; letter-spacing: -0.01em; font-size: 1.9rem; }
h2, h3 { font-weight: 600; letter-spacing: -0.005em; color: #1f3a5f; }
[data-testid="stMetric"] { background: #f6f7f9; border: 1px solid #dde2ea; border-radius: 6px;
                           padding: 0.8rem 1rem; }
[data-testid="stMetricLabel"] p { font-size: 0.8rem; color: #4a5563; }
[data-testid="stMetricValue"] { font-size: 1.45rem; font-weight: 600; color: #1f3a5f; }
.stTabs [data-baseweb="tab-list"] { gap: 0.25rem; border-bottom: 1px solid #dde2ea; overflow-x: auto; }
.stTabs [data-baseweb="tab"] { padding: 0.55rem 1rem; font-weight: 500; }
.stTabs [aria-selected="true"] { color: #1f3a5f; }
.chip { display: inline-block; padding: 0.2rem 0.7rem; border-radius: 999px; font-size: 0.8rem;
        font-weight: 500; border: 1px solid #dde2ea; background: #f3f5f8; color: #1b2430; }
.chip.live { background: #e3f4f1; border-color: #9fd6cd; color: #145a51; }
.chip.snap { background: #e8eef6; border-color: #b9c7da; color: #1f3a5f; }
.chip.sample { background: #fdf1db; border-color: #f0cf8f; color: #6b4a07; }
.subtitle { color: #4a5563; font-size: 0.95rem; margin-top: -0.4rem; }
button:focus-visible, [role="tab"]:focus-visible, input:focus-visible, [role="radio"]:focus-visible {
    outline: 2px solid #1f3a5f !important; outline-offset: 2px; }
footer, #MainMenu { visibility: hidden; }
@media (max-width: 640px) {
  .block-container { padding: 1rem 0.75rem; }
  h1 { font-size: 1.5rem; }
}
</style>
""", unsafe_allow_html=True)


def style_fig(fig, height=None):
    fig.update_layout(template="simple_white", font={"family": "Inter, Segoe UI, Arial, sans-serif",
                      "size": 13, "color": "#1b2430"}, margin={"l": 10, "r": 10, "t": 50, "b": 10},
                      **({"height": height} if height else {}))
    return fig


def status_chip(source: str, as_of: str | None) -> str:
    if source == "sample":
        return '<span class="chip sample">Sample data (synthetic)</span>'
    if source == "snapshot":
        return f'<span class="chip snap">Snapshot &middot; {as_of or "undated"}</span>'
    return '<span class="chip live">Live &middot; Yahoo Finance</span>'

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
SAMPLE_LABEL = "Sample (synthetic demo data)"


def _use_sample():
    st.session_state["data_mode"] = SAMPLE_LABEL


def _reset_overrides():
    for k in [k for k in st.session_state if str(k).startswith("ov_")]:
        del st.session_state[k]


st.sidebar.title("India Deal Lab")
st.sidebar.caption(f"Version {__version__}. Valuation, LBO and investment memo.")
st.session_state.setdefault("data_mode", list(MODES)[0])
mode_label = st.sidebar.radio("Data source", list(MODES), key="data_mode")
mode = MODES[mode_label]

if mode == "sample":
    cfg = SAMPLE_PRESET
    st.sidebar.selectbox("Case study", ["Sample Co A (synthetic)"], disabled=True)
    peers_default = cfg["peers"]
    note = "Synthetic companies for demonstration only."
else:
    names = list(PRESETS)
    try:
        qp = st.query_params.get("case")
    except Exception:
        qp = None
    start_name = qp if qp in names else DEFAULT_PRESET
    preset_name = st.sidebar.selectbox("Case study", names, index=names.index(start_name))
    try:
        st.query_params["case"] = preset_name
    except Exception:
        pass
    cfg = PRESETS[preset_name]
    peers_default = cfg["peers"]
    note = cfg["note"]
st.sidebar.caption(note)

hurdle_pct = st.sidebar.slider("Sponsor hurdle IRR", 10, 35, 20, 1, format="%d%%",
                               help="Minimum annual return a buyout sponsor needs to approve the deal.")
hurdle = hurdle_pct / 100

head_l, head_r = st.columns([3, 1])
head_l.title("India Deal Lab")
chip_slot = head_r.empty()
st.markdown('<p class="subtitle">Trading comparables, DCF, leveraged buyout, football field and investment '
            'committee memo for NSE-listed companies. For educational use only; not investment advice.</p>',
            unsafe_allow_html=True)

try:
    with st.spinner("Loading company data..."):
        target = load(cfg["ticker"], mode)
except Exception as exc:
    with st.container(border=True):
        st.markdown("#### We could not load data for this company")
        st.write("Live market data was unavailable and no saved snapshot exists for it. "
                 "You can explore the app with synthetic sample data, or pick another company in the sidebar.")
        st.button("Use sample data", type="primary", on_click=_use_sample)
        with st.expander("Technical details"):
            st.code(str(exc))
            st.caption("To create snapshots, run `python scripts/refresh_snapshots.py` or the "
                       "Refresh data snapshots workflow on GitHub.")
    st.stop()

chip_slot.markdown(f'<div style="text-align:right;padding-top:1.6rem">{status_chip(target.source, target.as_of)}</div>',
                   unsafe_allow_html=True)
if target.source == "sample":
    st.warning("Synthetic sample data. The companies and figures are illustrative and not real.")

peer_objs: list[CompanyData] = []
failed: list[str] = []
with st.spinner("Loading peers..."):
    for tk in peers_default:
        try:
            p = load(tk, mode)
            if p.is_complete():
                peer_objs.append(p)
            else:
                failed.append(tk)
        except Exception:
            failed.append(tk)

# ---- manual overrides ---------------------------------------------------
with st.sidebar.expander("Advanced assumptions"):
    st.caption("Override the fetched company figures.")
    price = st.number_input("Share price (Rs)", value=float(target.price), min_value=0.01, key=f"ov_price_{target.ticker}")
    shares = st.number_input("Shares (crore)", value=float(target.shares_cr), min_value=0.0001,
                             format="%.4f", key=f"ov_shares_{target.ticker}")
    rev0 = st.number_input("LTM revenue (Rs cr)", value=float(target.ltm_revenue), min_value=1.0, key=f"ov_rev_{target.ticker}")
    ebitda0 = st.number_input("LTM EBITDA (Rs cr)", value=float(target.ltm_ebitda), min_value=1.0,
                              key=f"ov_ebitda_{target.ticker}")
    debt = st.number_input("Total debt (Rs cr)", value=float(target.total_debt), min_value=0.0, key=f"ov_debt_{target.ticker}")
    cash = st.number_input("Cash (Rs cr)", value=float(target.cash), min_value=0.0, key=f"ov_cash_{target.ticker}")
    st.button("Reset overrides", on_click=_reset_overrides)

t = replace(target, price=price, shares_cr=shares, market_cap=price * shares,
            total_debt=debt, cash=cash,
            revenue=[*target.revenue[:-1], rev0], ebitda=[*target.ebitda[:-1], ebitda0])

# ---- comps (computed once, reused by every tab) ------------------------------
comp_df = comps_table(peer_objs) if peer_objs else pd.DataFrame()
exclude: list[str] = []
tabs = st.tabs(["Summary", "Valuation", "LBO", "Football field", "IC memo & export"])

# ======================================================================= comps
vt = tabs[1].tabs(["Comps", "DCF"])
stats = None
implied: dict = {}
with vt[0]:
    st.subheader("Trading comparables")
    if failed:
        st.caption("Peers skipped (incomplete or unavailable data): " + ", ".join(failed))
    if comp_df.empty or len(comp_df) < 2:
        st.warning("Not enough complete peers to build comps for this company. Try another case study or data source.")
    else:
        flags = flag_outliers(comp_df["EV/EBITDA"])
        out_tickers = list(comp_df.loc[flags, "Ticker"])
        all_peers = list(comp_df["Ticker"])
        chosen = st.pills("Peers included in statistics", all_peers, selection_mode="multi",
                          default=[p for p in all_peers if p not in out_tickers],
                          help="Peers outside 1.5 x IQR on EV/EBITDA start deselected. Click a peer to include or exclude it.")
        if not chosen:
            st.info("No peers selected, so all peers are used.")
            chosen = all_peers
        exclude = [p for p in all_peers if p not in chosen]

        subject = comps_table([t])
        show = comp_df.copy()
        show["Outlier"] = flags.map({True: "Outlier", False: ""})
        subject["Outlier"] = "Subject"
        show = pd.concat([subject, show], ignore_index=True)
        subj_ticker = t.ticker

        def _pin(row):
            return (["background-color:#e8eef6;font-weight:600"] * len(row)
                    if row["Ticker"] == subj_ticker else [""] * len(row))

        st.dataframe(show.style.apply(_pin, axis=1).format({
            "Mkt cap (Rs cr)": "{:,.0f}", "EV (Rs cr)": "{:,.0f}", "EBITDA margin %": "{:.1f}",
            "EV/EBITDA": "{:.1f}x", "EV/Sales": "{:.2f}x", "P/E": "{:.1f}x"}, na_rep="n/a"),
            hide_index=True, width="stretch")

        stats = summary_stats(comp_df, exclude)
        left_c, right_c = st.columns([3, 2])
        with left_c:
            st.markdown("**Summary statistics**")
            st.dataframe(stats.style.format("{:.1f}", na_rep="n/a"), width="stretch")
        with right_c:
            colors = [PALETTE["navy"] if p in chosen else PALETTE["line"] for p in comp_df["Ticker"]]
            bf = go.Figure(go.Bar(x=comp_df["Ticker"], y=comp_df["EV/EBITDA"], marker_color=colors,
                                  text=[f"{v:.1f}x" for v in comp_df["EV/EBITDA"]], textposition="outside"))
            bf.add_hline(y=t.enterprise_value / t.ltm_ebitda, line_dash="dash", line_color=PALETTE["pos"],
                         annotation_text=f"{t.ticker} {t.enterprise_value / t.ltm_ebitda:.1f}x")
            bf.update_layout(title="EV/EBITDA by peer (grey = excluded)", showlegend=False,
                             yaxis_title="EV/EBITDA (x)")
            st.plotly_chart(style_fig(bf, 320), width="stretch", key="comps_bar")
        implied = implied_valuation(t, stats)
        if implied:
            rows = [{"Multiple": k, "Q1": v["Q1"], "Median": v["Median"], "Q3": v["Q3"]}
                    for k, v in implied.items()]
            st.markdown("**Implied value per share (Rs)**")
            st.dataframe(pd.DataFrame(rows).style.format({"Q1": "{:,.0f}", "Median": "{:,.0f}",
                                                          "Q3": "{:,.0f}"}, na_rep="n/a"), hide_index=True)

# ========================================================================= dcf
with vt[1]:
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
                 .style.format("{:,.0f}", na_rep="n/a")
                 .background_gradient(cmap="RdYlGn", vmin=t.price * 0.5, vmax=t.price * 1.5, axis=None))
    s2.markdown("**Value per share: WACC vs exit multiple**")
    s2.dataframe(sensitivity_wacc_exit(dcf_in, waccs, [exit_mult + d for d in (-4, -2, 0, 2, 4)])
                 .style.format("{:,.0f}", na_rep="n/a")
                 .background_gradient(cmap="RdYlGn", vmin=t.price * 0.5, vmax=t.price * 1.5, axis=None))
    st.caption(f"Green cells are above the current price (Rs {t.price:,.0f}); red cells are below it. "
               "The numbers are shown in every cell, so colour is only a visual aid.")

# ========================================================================= lbo
with tabs[2]:
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
    m1_.metric("IRR", irr_txt, (f"{lbo['irr'] - hurdle:+.1%} vs {hurdle:.0%} hurdle" if lbo["irr"] == lbo["irr"] else None),
                help="Annualised return to the sponsor's equity over the hold period.")
    m2_.metric("MOIC", f"{lbo['moic']:.2f}x", help="Multiple of invested capital: exit equity divided by sponsor equity.")
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
    st.plotly_chart(fig, width="stretch", key="lbo_waterfall")
    with st.expander("View returns attribution as a table"):
        st.dataframe(pd.DataFrame({"Rs cr": {**attr, "Equity gain": lbo["equity_gain"]}})
                     .style.format("{:,.0f}"))

    st.markdown("**IRR sensitivity: entry multiple vs exit multiple**")
    ems = [entry_mult + d for d in (-2, -1, 0, 1, 2)]
    xms = [exit_m + d for d in (-2, -1, 0, 1, 2)]
    grid = irr_grid(lbo_in, ems, xms)
    st.dataframe(grid.style.format("{:.1%}", na_rep="n/a").map(
        lambda v: "background-color:#d8efe9;font-weight:600" if v == v and v >= hurdle else ""))
    st.caption(f"Highlighted cells meet the {hurdle:.0%} hurdle.")

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
with tabs[3]:
    st.subheader("Football field (Rs per share)")
    football = build_football(t, implied, dcf_in, lbo_in, irr_low=hurdle, irr_high=hurdle + 0.05)
    ff = go.Figure()
    for r in football:
        ff.add_trace(go.Bar(y=[r["method"]], x=[r["high"] - r["low"]], base=[r["low"]],
                            orientation="h", showlegend=False, marker_color=PALETTE["navy"],
                            text=f"{r['low']:,.0f} to {r['high']:,.0f}", textposition="outside", textangle=0,
                            cliponaxis=False,
                            hovertemplate=f"{r['method']}<br>Rs %{{base:,.0f}} to Rs {r['high']:,.0f}<extra></extra>"))
    for xv, dash, col, lab, shift in ((t.price, "solid", PALETTE["pos"], f"Price Rs {t.price:,.0f}", 0),
                                      (entry_price, "dash", PALETTE["warn"], f"Offer Rs {entry_price:,.0f}", 18)):
        ff.add_shape(type="line", x0=xv, x1=xv, y0=0, y1=1, xref="x", yref="paper",
                     line={"color": col, "width": 2.5, "dash": dash}, layer="above")
        ff.add_annotation(x=xv, y=1, xref="x", yref="paper", text=lab, showarrow=False, yshift=14 + shift,
                          font={"color": "#1b2430", "size": 12})
    ff.update_layout(xaxis_title="Rs per share", yaxis={"autorange": "reversed"})
    style_fig(ff, 120 + 70 * len(football))
    ff.update_layout(margin={"l": 10, "r": 90, "t": 80, "b": 10})
    st.plotly_chart(ff, width="stretch", key="football_main")
    st.dataframe(pd.DataFrame(football).rename(columns={"method": "Method", "low": "Low", "high": "High",
                                                        "mid": "Mid"})
                 .style.format({"Low": "{:,.0f}", "High": "{:,.0f}", "Mid": "{:,.0f}"}), hide_index=True)

# =================================================================== memo + export
with tabs[4]:
    st.subheader("Investment committee memo")
    stats_for_memo = stats if comp_df is not None and not comp_df.empty and len(comp_df) >= 2 else None
    memo_md = build_memo(t, peer_objs, stats_for_memo, implied, dcf_in, dcf, lbo_in, lbo, football,
                         premium, hurdle, max_entry)
    blob = build_workbook(t, dcf_in, lbo_in, t.price)
    d1, d2, _sp = st.columns([1, 1, 2])
    d1.download_button("Download memo (.md)", memo_md, file_name=f"IC_memo_{t.ticker}.md",
                       mime="text/markdown", width="stretch")
    d2.download_button("Download model (.xlsx)", blob, file_name=f"DealLab_{t.ticker}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")
    with st.container(border=True):
        st.markdown(memo_md)
    with st.expander("What is in the Excel model?"):
        st.write("A formula-live workbook with Assumptions, DCF and LBO sheets. Change a blue input and the "
                 "model recalculates in Excel. It mirrors the Python model; the Excel LBO uses a fixed "
                 "5-year horizon with the exit year taken from the hold period.")

# ===================================================================== summary
# Rendered last (so every model result exists) but displayed in the first tab.
with tabs[0]:
    st.subheader(f"{t.name} ({t.ticker})")
    comps_med = implied.get("EV/EBITDA", {}).get("Median") if implied else None
    irr_ok = lbo["irr"] == lbo["irr"] and lbo["irr"] >= hurdle
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Market price", f"Rs {t.price:,.1f}", help="Current share price (editable under Advanced assumptions).")
    k2.metric("DCF value / share", f"Rs {dcf['price_blended']:,.0f}",
              f"{dcf['price_blended'] / t.price - 1:+.0%} vs price", help="Average of Gordon-growth and exit-multiple DCF values.")
    if comps_med and comps_med == comps_med:
        k3.metric("Comps value / share", f"Rs {comps_med:,.0f}", f"{comps_med / t.price - 1:+.0%} vs price",
                  help="Median peer EV/EBITDA applied to the company's LTM EBITDA.")
    else:
        k3.metric("Comps value / share", "n/a", "not enough peers", delta_color="off")
    k4.metric("LBO IRR", f"{lbo['irr']:.1%}" if lbo["irr"] == lbo["irr"] else "n/a",
              (f"{lbo['irr'] - hurdle:+.1%} vs {hurdle:.0%} hurdle" if lbo["irr"] == lbo["irr"] else None),
              help="Sponsor return at the control premium and leverage chosen on the LBO tab.")

    col_chart, col_take = st.columns([3, 2])
    with col_chart:
        ff_sum = go.Figure(ff)
        ff_sum.update_layout(height=120 + 55 * len(football), title="Valuation range (Rs per share)")
        st.plotly_chart(ff_sum, width="stretch", key="football_summary")
    with col_take:
        with st.container(border=True):
            st.markdown("**Key takeaways**")
            bullets = [f"DCF points to **Rs {dcf['price_blended']:,.0f}** per share, "
                       f"{dcf['price_blended'] / t.price - 1:+.0%} versus the market price."]
            if comps_med and comps_med == comps_med:
                bullets.append(f"Peer-median EV/EBITDA implies **Rs {comps_med:,.0f}** ({comps_med / t.price - 1:+.0%}).")
            bullets.append(f"A buyout at a {premium:.0%} premium returns **{irr_txt}** IRR, "
                           f"{'clearing' if irr_ok else 'missing'} the {hurdle:.0%} hurdle.")
            if max_entry:
                bullets.append(f"The highest entry multiple that still clears the hurdle is **{max_entry:.1f}x** "
                               f"(currently {entry_mult:.1f}x).")
            st.markdown("\n".join(f"- {b}" for b in bullets))

    st.markdown("#### Company snapshot")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Market cap", fmt_cr(t.market_cap))
    c2.metric("Net debt", fmt_cr(t.net_debt), help="Total debt minus cash.")
    c3.metric("EV / LTM EBITDA", f"{t.enterprise_value / t.ltm_ebitda:.1f}x",
              help="Enterprise value divided by trailing-twelve-month EBITDA.")
    c4.metric("EBITDA margin", f"{t.ltm_ebitda / t.ltm_revenue:.1%}")
    if t.summary:
        st.write(t.summary)
    if t.revenue and len(t.ebitda) >= len(t.revenue):
        n_h = len(t.revenue)
        yrs_h = t.years[-n_h:] if len(t.years) >= n_h else [f"Year {i + 1}" for i in range(n_h)]
        hf = go.Figure([go.Bar(name="Revenue", x=yrs_h, y=t.revenue, marker_color=PALETTE["navy"]),
                        go.Bar(name="EBITDA", x=yrs_h, y=t.ebitda[-n_h:], marker_color=PALETTE["steel"])])
        hf.update_layout(barmode="group", title="Revenue and EBITDA history (Rs crore)",
                         xaxis={"type": "category"}, legend={"orientation": "h", "y": -0.15})
        st.plotly_chart(style_fig(hf, 320), width="stretch", key="history")
        with st.expander("View history as a table"):
            st.dataframe(pd.DataFrame({"Revenue": t.revenue, "EBITDA": t.ebitda[-n_h:]}, index=yrs_h)
                         .style.format("{:,.0f}"))
    notes = list(t.warnings) + ([f"Peers skipped (incomplete or unavailable data): {', '.join(failed)}"] if failed else [])
    if notes:
        with st.expander(f"Data quality notes ({len(notes)})"):
            for w in notes:
                st.write("- " + w)


st.divider()
st.caption("India Deal Lab is an educational project. Data is sourced from Yahoo Finance via yfinance or from "
           "bundled snapshots and may be incomplete or restated. Nothing here constitutes investment advice.")
