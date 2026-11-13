"""Preset universe: target companies and their peer sets.

Chosen to be liquid NSE-listed non-financial companies with positive EBITDA,
so DCF, comps and LBO logic all apply (banks and NBFCs are excluded on purpose:
EV/EBITDA and free-cash-flow models do not fit lenders).
"""
from __future__ import annotations

PRESETS = {
    "Berger Paints India (Paints)": {
        "ticker": "BERGEPAINT.NS",
        "peers": ["ASIANPAINT.NS", "KANSAINER.NS", "PIDILITIND.NS"],
        "note": "Mid-cap decorative paints leader; shows a larger-ticket LBO strain.",
    },
    "Dabur India (FMCG)": {
        "ticker": "DABUR.NS",
        "peers": ["MARICO.NS", "GODREJCP.NS", "COLPAL.NS", "HINDUNILVR.NS"],
        "note": "Stable FMCG cash flows, low capex.",
    },
    "Marico (FMCG)": {
        "ticker": "MARICO.NS",
        "peers": ["DABUR.NS", "GODREJCP.NS", "COLPAL.NS", "HINDUNILVR.NS"],
        "note": "Asset-light FMCG with high returns on capital.",
    },
    "Havells India (Electricals)": {
        "ticker": "HAVELLS.NS",
        "peers": ["POLYCAB.NS", "VOLTAS.NS", "CROMPTON.NS", "KEI.NS"],
        "note": "Cyclical-adjacent consumer electricals; margin sensitivity matters.",
    },
    "Pidilite Industries (Adhesives)": {
        "ticker": "PIDILITIND.NS",
        "peers": ["ASIANPAINT.NS", "BERGEPAINT.NS", "KANSAINER.NS"],
        "note": "Premium-multiple specialty chemicals/adhesives franchise.",
    },
}

DEFAULT_PRESET = "Berger Paints India (Paints)"


def all_tickers() -> list[str]:
    seen: list[str] = []
    for cfg in PRESETS.values():
        for t in [cfg["ticker"], *cfg["peers"]]:
            if t not in seen:
                seen.append(t)
    return seen
