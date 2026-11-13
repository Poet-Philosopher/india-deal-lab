import numpy as np
import pandas as pd
import pytest

from deal_lab.comps import comps_table, flag_outliers, implied_valuation, multiples, summary_stats
from deal_lab.data import sample_universe


def test_multiples_by_hand(target):
    m = multiples(target)
    ev = target.market_cap + target.total_debt - target.cash
    assert m["EV/EBITDA"] == pytest.approx(ev / target.ltm_ebitda)
    assert m["EV/Sales"] == pytest.approx(ev / target.ltm_revenue)
    assert m["P/E"] == pytest.approx(target.market_cap / target.ltm_net_income)


def test_table_and_stats():
    u = sample_universe()
    peers = [u[k] for k in ("SAMPLE-B", "SAMPLE-C", "SAMPLE-D", "SAMPLE-E")]
    df = comps_table(peers)
    st = summary_stats(df)
    assert st.loc["EV/EBITDA", "Count"] == 4
    assert st.loc["EV/EBITDA", "Q1"] <= st.loc["EV/EBITDA", "Median"] <= st.loc["EV/EBITDA", "Q3"]
    ex = summary_stats(df, exclude=["SAMPLE-B"])
    assert ex.loc["EV/EBITDA", "Count"] == 3


def test_outlier_flag():
    s = pd.Series([10, 11, 12, 11, 10, 60], index=list("abcdef"))
    flags = flag_outliers(s)
    assert flags["f"] and not flags["a"]


def test_implied_per_share_consistent(target):
    u = sample_universe()
    peers = [u[k] for k in ("SAMPLE-B", "SAMPLE-C", "SAMPLE-D", "SAMPLE-E")]
    st = summary_stats(comps_table(peers))
    imp = implied_valuation(target, st)
    med = st.loc["EV/EBITDA", "Median"]
    expected = (med * target.ltm_ebitda - target.net_debt) / target.shares_cr
    assert imp["EV/EBITDA"]["Median"] == pytest.approx(expected)
    assert imp["EV/EBITDA"]["Q1"] <= imp["EV/EBITDA"]["Q3"]
