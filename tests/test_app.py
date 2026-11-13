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
    assert len(at.tabs) == 7
    assert at.tabs[5].markdown, "IC memo tab rendered no content"


def test_app_shows_clear_error_without_snapshot(tmp_path, monkeypatch):
    from deal_lab import data
    monkeypatch.setattr(data, "SNAPSHOT_DIR", tmp_path)  # empty: no bundled snapshots
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value("Bundled snapshot only").run()
    assert not at.exception
    assert at.error, "expected a friendly error when no data is available"
