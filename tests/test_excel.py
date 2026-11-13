"""Recalculate the exported workbook with LibreOffice and compare with the Python models."""
import shutil
import subprocess
from pathlib import Path

import pytest
from openpyxl import load_workbook

from deal_lab.dcf import run_dcf
from deal_lab.excel_export import build_workbook
from deal_lab.lbo import run_lbo

pytestmark = pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")


def recalc(xlsx_bytes: bytes, tmp_path: Path) -> Path:
    src = tmp_path / "in" / "model.xlsx"
    src.parent.mkdir()
    src.write_bytes(xlsx_bytes)
    out = tmp_path / "out"
    out.mkdir()
    subprocess.run(["soffice", "--headless", "--convert-to", "xlsx", "--outdir", str(out), str(src)],
                   check=True, capture_output=True, timeout=180)
    return out / "model.xlsx"


@pytest.mark.parametrize("mid_year", [False, True])
def test_workbook_matches_python(tmp_path, target, dcf_inputs, lbo_inputs, mid_year):
    from dataclasses import replace
    d = replace(dcf_inputs, mid_year=mid_year)
    blob = build_workbook(target, d, lbo_inputs, target.price)
    wb = load_workbook(recalc(blob, tmp_path), data_only=True)
    dcf, lbo = run_dcf(d), run_lbo(lbo_inputs)

    s, b = wb["DCF"], wb["LBO"]
    assert s["B23"].value == pytest.approx(dcf["price_gordon"], rel=1e-6)
    assert s["B29"].value == pytest.approx(dcf["price_exit"], rel=1e-6)
    assert s["B31"].value == pytest.approx(dcf["price_blended"], rel=1e-6)
    assert b["B9"].value == pytest.approx(lbo["equity0"], rel=1e-6)
    assert b["B10"].value == pytest.approx(0, abs=1e-6)
    assert b["B38"].value == pytest.approx(lbo["equity_exit"], rel=1e-6)
    assert b["B39"].value == pytest.approx(lbo["moic"], rel=1e-6)
    assert b["B40"].value == pytest.approx(lbo["irr"], rel=1e-6)
    assert b["B48"].value == pytest.approx(0, abs=1e-6)


def test_workbook_has_live_formulas(target, dcf_inputs, lbo_inputs):
    import io
    wb = load_workbook(io.BytesIO(build_workbook(target, dcf_inputs, lbo_inputs, target.price)))
    assert str(wb["DCF"]["C12"].value).startswith("=")
    assert str(wb["LBO"]["B40"].value).startswith("=")
    assert not str(wb["Assumptions"]["B9"].value).startswith("=")
