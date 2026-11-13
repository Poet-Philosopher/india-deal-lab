import pandas as pd
import pytest

from deal_lab import data
from deal_lab.data import company_from_frames, get_company, sample_universe


def frame(rows: dict, years=(2025, 2024, 2023)):
    cols = [pd.Timestamp(f"{y}-03-31") for y in years]  # newest first, like yfinance
    return pd.DataFrame({c: [rows[k][i] for k in rows] for i, c in enumerate(cols)},
                        index=list(rows))


def build():
    cr = 1e7
    fin = frame({"Total Revenue": [3000 * cr, 2800 * cr, 2600 * cr],
                 "EBITDA": [500 * cr, 460 * cr, 420 * cr],
                 "EBIT": [440 * cr, 400 * cr, 360 * cr],
                 "Net Income": [330 * cr, 300 * cr, 270 * cr],
                 "Pretax Income": [440 * cr, 400 * cr, 360 * cr],
                 "Tax Provision": [110 * cr, 100 * cr, 90 * cr]})
    bal = frame({"Total Debt": [100 * cr, 110 * cr, 120 * cr],
                 "Cash Cash Equivalents And Short Term Investments": [400 * cr, 380 * cr, 350 * cr],
                 "Accounts Receivable": [300 * cr, 280 * cr, 260 * cr],
                 "Inventory": [250 * cr, 240 * cr, 230 * cr],
                 "Accounts Payable": [320 * cr, 300 * cr, 280 * cr]})
    cf = frame({"Depreciation And Amortization": [60 * cr, 60 * cr, 60 * cr],
                "Capital Expenditure": [-90 * cr, -80 * cr, -70 * cr]})
    info = {"longName": "Test Ltd", "currentPrice": 2000.0, "sharesOutstanding": 4.5 * cr,
            "marketCap": 9000 * cr, "beta": 0.9, "sector": "Basic Materials"}
    return company_from_frames("TEST.NS", info, fin, bal, cf)


def test_parser_units_order_and_signs():
    cd = build()
    assert cd.revenue == [2600, 2800, 3000]  # oldest -> newest, in crore
    assert cd.years == ["2023", "2024", "2025"]
    assert cd.capex == [70, 80, 90]  # sign flipped to positive
    assert cd.market_cap == pytest.approx(9000)
    assert cd.shares_cr == pytest.approx(4.5)
    assert cd.net_debt == pytest.approx(100 - 400)
    assert cd.enterprise_value == pytest.approx(9000 - 300)
    assert cd.tax_rate == pytest.approx(0.25)
    assert cd.nwc == pytest.approx(300 + 250 - 320)
    assert cd.is_complete()


def test_missing_fields_are_flagged_not_filled():
    cd = company_from_frames("X.NS", {"currentPrice": 100.0, "marketCap": 1e9}, None, None, None)
    assert not cd.is_complete()
    assert any("revenue" in w.lower() for w in cd.warnings)
    assert any("debt" in w.lower() for w in cd.warnings)
    assert cd.total_debt is None and cd.cash is None


def test_ebitda_derived_only_with_warning():
    cr = 1e7
    fin = frame({"Total Revenue": [3000 * cr, 2800 * cr, 2600 * cr],
                 "EBIT": [440 * cr, 400 * cr, 360 * cr]})
    cf = frame({"Depreciation And Amortization": [60 * cr, 60 * cr, 60 * cr]})
    cd = company_from_frames("X.NS", {}, fin, None, cf)
    assert cd.ebitda == [420, 460, 500]
    assert any("derived" in w.lower() for w in cd.warnings)


def test_snapshot_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "SNAPSHOT_DIR", tmp_path)
    cd = build()
    data.save_snapshot(cd)
    back = data.load_snapshot("TEST.NS")
    assert back.revenue == cd.revenue and back.source == "snapshot"


def test_sample_universe_is_complete_and_labelled():
    for cd in sample_universe().values():
        assert cd.is_complete()
        assert cd.source == "sample"
        assert any("SYNTHETIC" in w for w in cd.warnings)


def test_get_company_sample_and_clear_error(monkeypatch, tmp_path):
    assert get_company("SAMPLE-A", "sample").ticker == "SAMPLE-A"
    monkeypatch.setattr(data, "SNAPSHOT_DIR", tmp_path)
    with pytest.raises(RuntimeError):
        get_company("NOPE.NS", "snapshot")
