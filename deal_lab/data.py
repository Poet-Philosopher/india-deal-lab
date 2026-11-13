"""Data layer: Yahoo Finance (via yfinance), bundled snapshots, and labelled sample data.

Rules: never silently fill gaps. Anything missing is recorded in CompanyData.warnings
and the UI lets the user override inputs by hand.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from .models import CRORE, CompanyData

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "data" / "snapshots"

# yfinance row-name candidates (labels vary by company and library version)
ROWS = {
    "revenue": ["Total Revenue", "Operating Revenue", "Revenue"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "ebit": ["EBIT", "Operating Income"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    "pretax": ["Pretax Income"],
    "tax": ["Tax Provision"],
    "da": ["Depreciation And Amortization", "Depreciation Amortization Depletion",
           "Reconciled Depreciation"],
    "capex": ["Capital Expenditure", "Purchase Of PPE"],
    "debt": ["Total Debt"],
    "cash": ["Cash Cash Equivalents And Short Term Investments",
             "Cash And Cash Equivalents"],
    "receivables": ["Accounts Receivable", "Receivables"],
    "inventory": ["Inventory"],
    "payables": ["Accounts Payable", "Payables"],
}


def _clean_number(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _series(df: Optional[pd.DataFrame], key: str):
    """Return (labels, values_in_crore) oldest -> newest for the first matching row."""
    if df is None or getattr(df, "empty", True):
        return [], []
    for name in ROWS[key]:
        if name in df.index:
            row = df.loc[name]
            pairs = []
            for col, val in row.items():
                v = _clean_number(val)
                if v is not None:
                    label = str(col.year) if hasattr(col, "year") else str(col)
                    pairs.append((col, label, v / CRORE))
            if pairs:
                pairs.sort(key=lambda p: p[0])
                return [p[1] for p in pairs], [p[2] for p in pairs]
    return [], []


def _latest(df: Optional[pd.DataFrame], key: str) -> Optional[float]:
    _, vals = _series(df, key)
    return vals[-1] if vals else None


def company_from_frames(ticker: str, info: dict, financials: Optional[pd.DataFrame],
                        balance: Optional[pd.DataFrame], cashflow: Optional[pd.DataFrame],
                        source: str = "live") -> CompanyData:
    """Pure parser (no network) so it can be unit-tested with synthetic frames."""
    warn: list[str] = []
    info = info or {}

    labels, revenue = _series(financials, "revenue")
    _, ebitda = _series(financials, "ebitda")
    _, ebit = _series(financials, "ebit")
    _, ni = _series(financials, "net_income")
    _, da = _series(cashflow, "da")
    _, capex = _series(cashflow, "capex")
    capex = [abs(c) for c in capex]

    # align lengths to revenue history from the newest end
    n = len(revenue)
    def tail(xs):
        return xs[-n:] if len(xs) >= n else xs

    if not revenue:
        warn.append("No revenue history returned.")
    if not ebitda:
        if ebit and da and len(ebit) == len(da):
            ebitda = [a + b for a, b in zip(ebit, da)]
            warn.append("EBITDA derived as EBIT + D&A (not reported directly).")
        else:
            warn.append("No EBITDA history returned.")
    if not capex:
        warn.append("No capex history returned.")
    if not da:
        warn.append("No D&A history returned.")

    price = _clean_number(info.get("currentPrice") or info.get("regularMarketPrice"))
    shares = _clean_number(info.get("sharesOutstanding"))
    shares_cr = shares / CRORE if shares else None
    mcap = _clean_number(info.get("marketCap"))
    mcap_cr = mcap / CRORE if mcap else None
    if mcap_cr is None and price and shares_cr:
        mcap_cr = price * shares_cr
        warn.append("Market cap computed as price x shares.")
    if shares_cr is None and price and mcap_cr:
        shares_cr = mcap_cr / price
        warn.append("Share count backed out of market cap / price.")

    debt = _latest(balance, "debt")
    if debt is None and _clean_number(info.get("totalDebt")) is not None:
        debt = info["totalDebt"] / CRORE
        warn.append("Debt taken from summary info (may include leases).")
    cash = _latest(balance, "cash")
    if cash is None and _clean_number(info.get("totalCash")) is not None:
        cash = info["totalCash"] / CRORE
        warn.append("Cash taken from summary info.")
    if debt is None:
        warn.append("Total debt missing.")
    if cash is None:
        warn.append("Cash missing.")

    # tax rate
    tax_rate = 0.2517
    _, tax = _series(financials, "tax")
    _, pretax = _series(financials, "pretax")
    if tax and pretax and pretax[-1] > 0:
        tax_rate = min(max(tax[-1] / pretax[-1], 0.15), 0.35)
    else:
        warn.append("Tax rate defaulted to 25.17% (statutory new-regime rate).")

    # net working capital (latest): receivables + inventory - payables
    rec, inv, pay = (_latest(balance, k) for k in ("receivables", "inventory", "payables"))
    nwc = None
    if rec is not None and pay is not None:
        nwc = rec + (inv or 0.0) - pay
    else:
        warn.append("Working-capital components missing; NWC % defaults will be used.")

    beta = _clean_number(info.get("beta"))
    if beta is None:
        warn.append("Beta missing; default 1.0 used until you override it.")

    cd = CompanyData(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName") or ticker,
        sector=info.get("sector", "") or "",
        industry=info.get("industry", "") or "",
        summary=(info.get("longBusinessSummary", "") or "")[:900],
        price=price, shares_cr=shares_cr, market_cap=mcap_cr,
        total_debt=debt, cash=cash,
        years=labels[-n:] if n else [],
        revenue=revenue, ebitda=tail(ebitda), ebit=tail(ebit), net_income=tail(ni),
        da=tail(da), capex=tail(capex), nwc=nwc, tax_rate=tax_rate,
        beta=beta,
        week52_low=_clean_number(info.get("fiftyTwoWeekLow")),
        week52_high=_clean_number(info.get("fiftyTwoWeekHigh")),
        source=source,
        as_of=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        warnings=warn,
    )
    return cd


def fetch_live(ticker: str) -> CompanyData:
    import yfinance as yf  # imported lazily so tests run without network

    t = yf.Ticker(ticker)
    info = t.info or {}
    cd = company_from_frames(ticker, info, t.financials, t.balance_sheet, t.cashflow, "live")
    if cd.beta is None:
        b = estimate_beta(ticker)
        if b is not None:
            cd.beta = b
            cd.warnings = [w for w in cd.warnings if not w.startswith("Beta missing")]
            cd.warnings.append("Beta estimated by regression (3y weekly returns vs Nifty 50).")
    return cd


def estimate_beta(ticker: str, index: str = "^NSEI") -> Optional[float]:
    try:
        import yfinance as yf

        px = yf.download([ticker, index], period="3y", interval="1wk",
                         auto_adjust=True, progress=False)["Close"].dropna()
        if len(px) < 40:
            return None
        rets = px.pct_change().dropna()
        cov = np.cov(rets[ticker], rets[index])
        return float(cov[0, 1] / cov[1, 1])
    except Exception:
        return None


# ---- snapshots -------------------------------------------------------------
def _snap_path(ticker: str) -> Path:
    return SNAPSHOT_DIR / f"{ticker.replace('^', '').replace('/', '_')}.json"


def save_snapshot(cd: CompanyData) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    p = _snap_path(cd.ticker)
    d = cd.to_dict()
    d["source"] = "snapshot"
    p.write_text(json.dumps(d, indent=2))
    return p


def load_snapshot(ticker: str) -> Optional[CompanyData]:
    p = _snap_path(ticker)
    if not p.exists():
        return None
    return CompanyData.from_dict(json.loads(p.read_text()))


# ---- sample (synthetic, clearly labelled) -----------------------------------
def sample_universe() -> dict[str, CompanyData]:
    """Synthetic companies for demos and tests. NOT real data and not real tickers."""
    def mk(key, name, rev0, g, margin, price, shares, debt, cash, beta, ni_margin):
        revs = [rev0 * (1 + g) ** i for i in range(4)]
        ebitda = [r * margin for r in revs]
        da = [r * 0.03 for r in revs]
        return CompanyData(
            ticker=key, name=name, sector="SAMPLE", industry="Synthetic demo data",
            summary="Synthetic company generated for demonstration. Not real data.",
            price=price, shares_cr=shares, market_cap=price * shares,
            total_debt=debt, cash=cash, years=["FY-3", "FY-2", "FY-1", "LTM"],
            revenue=revs, ebitda=ebitda, ebit=[e - d for e, d in zip(ebitda, da)],
            net_income=[r * ni_margin for r in revs], da=da,
            capex=[r * 0.035 for r in revs], nwc=revs[-1] * 0.12, tax_rate=0.2517,
            beta=beta, week52_low=price * 0.78, week52_high=price * 1.18,
            source="sample", as_of="synthetic",
            warnings=["SYNTHETIC SAMPLE DATA - illustrative only, not a real company."],
        )
    return {
        "SAMPLE-A": mk("SAMPLE-A", "Sample Co A (target)", 3000, 0.08, 0.17, 2400, 4.6, 120, 380, 0.85, 0.11),
        "SAMPLE-B": mk("SAMPLE-B", "Sample Co B", 32000, 0.09, 0.21, 1500, 95.0, 1500, 900, 0.80, 0.14),
        "SAMPLE-C": mk("SAMPLE-C", "Sample Co C", 9000, 0.10, 0.16, 600, 58.0, 700, 650, 0.95, 0.10),
        "SAMPLE-D": mk("SAMPLE-D", "Sample Co D", 6500, 0.07, 0.15, 330, 54.0, 400, 500, 0.90, 0.09),
        "SAMPLE-E": mk("SAMPLE-E", "Sample Co E", 14000, 0.11, 0.19, 5200, 11.4, 600, 1100, 0.88, 0.12),
    }


SAMPLE_PRESET = {"ticker": "SAMPLE-A",
                 "peers": ["SAMPLE-B", "SAMPLE-C", "SAMPLE-D", "SAMPLE-E"]}


def get_company(ticker: str, mode: str = "auto") -> CompanyData:
    """mode: auto (live, then snapshot) | live | snapshot | sample."""
    if mode == "sample":
        return sample_universe()[ticker]
    if mode in ("auto", "live"):
        try:
            cd = fetch_live(ticker)
            if cd.is_complete():
                return cd
            if mode == "live":
                return cd
        except Exception as exc:  # network, rate-limit, bad ticker
            if mode == "live":
                raise RuntimeError(f"Live fetch failed for {ticker}: {exc}") from exc
    snap = load_snapshot(ticker)
    if snap is not None:
        snap.warnings = [*snap.warnings, f"Using bundled snapshot dated {snap.as_of}."]
        return snap
    raise RuntimeError(
        f"No data for {ticker}: live fetch failed or incomplete and no snapshot is bundled. "
        "Switch the data source to 'Sample' or enter the figures manually."
    )


def get_peers(tickers: Iterable[str], mode: str = "auto") -> tuple[list[CompanyData], list[str]]:
    ok: list[CompanyData] = []
    failed: list[str] = []
    for t in tickers:
        try:
            cd = get_company(t, mode)
        except Exception:
            failed.append(t)
            continue
        if cd.is_complete():
            ok.append(cd)
        else:
            failed.append(t)
    return ok, failed
