"""Smoke test: the Streamlit app renders end to end on sample data without exceptions."""
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_runs_on_sample_data():
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("Sample (synthetic demo data)").run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Synthetic sample data" in w.value for w in at.warning)
    labels = [tab.label for tab in at.tabs]
    for expected in ("Summary", "Valuation", "LBO", "Football field", "IC memo & export", "Comps", "DCF"):
        assert expected in labels, labels
    memo_tab = at.tabs[labels.index("IC memo & export")]
    assert memo_tab.markdown, "IC memo tab rendered no content"
    summary_tab = at.tabs[labels.index("Summary")]
    assert summary_tab.metric, "Summary tab rendered no headline metrics"


def test_app_shows_clear_error_without_snapshot(tmp_path, monkeypatch):
    from deal_lab import data
    monkeypatch.setattr(data, "SNAPSHOT_DIR", tmp_path)  # empty: no bundled snapshots
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("Bundled snapshot only").run()
    assert not at.exception
    assert not at.error, "errors should be shown as a friendly card, not a raw error banner"
    assert any("could not load data" in m.value for m in at.markdown), "friendly error card missing"
    assert any(b.label == "Use sample data" for b in at.button), "sample-data recovery button missing"


def test_override_inputs_follow_selected_company(tmp_path, monkeypatch):
    """Switching case study must not carry the previous company's price/share overrides."""
    import json
    from deal_lab import data
    from deal_lab.data import sample_universe
    monkeypatch.setattr(data, "SNAPSHOT_DIR", tmp_path)
    for tk, cd in sample_universe().items():
        (tmp_path / f"{tk}.json").write_text(json.dumps(cd.to_dict()))
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("Sample (synthetic demo data)").run()
    keys = [n.key for n in at.sidebar.number_input]
    assert any(k.startswith("ov_price_") and k.endswith("SAMPLE-A") for k in keys), keys
