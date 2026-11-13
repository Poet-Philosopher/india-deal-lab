"""Formula-live Excel workbook: change a blue input and DCF + LBO recalculate.

The workbook mirrors deal_lab.dcf and deal_lab.lbo exactly. Tests recalculate it with
LibreOffice and compare the results against the Python models.
The Excel LBO uses a fixed 5-year projection with an exit year chosen by the hold input.
"""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .dcf import DCFInputs
from .lbo import LBOInputs
from .models import CompanyData

BLUE = Font(color="0000FF")
BOLD = Font(bold=True)
HEAD = PatternFill("solid", fgColor="DDE6F0")
PCT = "0.0%"
NUM = "#,##0.0"
MULT = '0.0"x"'


def _label(ws, row, text, bold=False):
    c = ws.cell(row=row, column=1, value=text)
    if bold:
        c.font = BOLD


def _input(ws, ref, value, fmt=None):
    ws[ref] = value
    ws[ref].font = BLUE
    if fmt:
        ws[ref].number_format = fmt


def build_workbook(company: CompanyData, d: DCFInputs, l: LBOInputs, price: float) -> bytes:
    wb = Workbook()
    a = wb.active
    a.title = "Assumptions"
    a["A1"] = f"{company.name} ({company.ticker}): assumptions (Rs crore)"
    a["A1"].font = Font(bold=True, size=13)
    a["A2"] = "Blue cells are inputs. Everything else is a live formula."

    scalars = [
        (3, "Base (LTM) revenue", d.base_revenue, NUM),
        (4, "Base (LTM) EBITDA", l.ebitda0, NUM),
        (5, "Tax rate", d.tax_rate, PCT),
        (6, "D&A % of revenue", d.da_pct, PCT),
        (7, "Capex % of revenue", d.capex_pct, PCT),
        (8, "NWC % of incremental revenue", d.nwc_pct_incr, PCT),
        (9, "WACC", d.wacc, PCT),
        (10, "Terminal growth", d.terminal_growth, PCT),
        (11, "DCF exit EV/EBITDA", d.exit_multiple, MULT),
        (12, "Net debt (existing)", d.net_debt, NUM),
        (13, "Shares outstanding (crore)", d.shares, "0.0000"),
        (14, "Mid-year convention (1 = on, 0 = off)", 1 if d.mid_year else 0, "0"),
        (15, "Current share price (Rs)", price, "#,##0.00"),
    ]
    for r, lab, val, fmt in scalars:
        _label(a, r, lab)
        _input(a, f"B{r}", val, fmt)
    _label(a, 17, "Projection year", True)
    for k in range(5):
        a.cell(row=17, column=2 + k, value=k + 1).font = BOLD
    _label(a, 18, "Revenue growth")
    _label(a, 19, "EBITDA margin")
    for k in range(5):
        _input(a, f"{get_column_letter(2 + k)}18", d.growth[k], PCT)
        _input(a, f"{get_column_letter(2 + k)}19", d.ebitda_margin[k], PCT)

    lbo_scalars = [
        (22, "Entry EV/EBITDA", l.entry_multiple, MULT),
        (23, "Senior debt (x EBITDA)", l.senior_x, MULT),
        (24, "Mezzanine (x EBITDA)", l.mezz_x, MULT),
        (25, "Senior interest rate", l.senior_rate, PCT),
        (26, "Mezzanine cash rate", l.mezz_cash_rate, PCT),
        (27, "Mezzanine PIK rate", l.mezz_pik_rate, PCT),
        (28, "Transaction fees (% of EV)", l.fee_pct, PCT),
        (29, "Minimum cash funded at close", l.min_cash, NUM),
        (30, "Mandatory amortisation (% of original senior)", l.amort_pct, PCT),
        (31, "Cash sweep (% of excess cash)", l.sweep_pct, PCT),
        (32, "LBO exit EV/EBITDA", l.exit_multiple, MULT),
        (33, "Hold period (years, 1 to 5)", l.hold_years, "0"),
    ]
    _label(a, 21, "LBO", True)
    for r, lab, val, fmt in lbo_scalars:
        _label(a, r, lab)
        _input(a, f"B{r}", val, fmt)
    a.column_dimensions["A"].width = 46
    for c in "BCDEF":
        a.column_dimensions[c].width = 13

    # ------------------------------------------------------------------ DCF
    s = wb.create_sheet("DCF")
    s["A1"] = "Discounted cash flow (unlevered FCF)"
    s["A1"].font = Font(bold=True, size=13)
    cols = ["B", "C", "D", "E", "F", "G"]
    _label(s, 3, "Year", True)
    for k, c in enumerate(cols):
        s[f"{c}3"] = k
        s[f"{c}3"].font = BOLD
        s[f"{c}3"].fill = HEAD
    rows = {4: "Revenue", 5: "EBITDA", 6: "D&A", 7: "EBIT", 8: "Tax on EBIT", 9: "NOPAT",
            10: "Capex", 11: "Increase in NWC", 12: "Free cash flow (FCFF)",
            13: "Discount period (years)", 14: "Discount factor", 15: "PV of FCFF"}
    for r, t in rows.items():
        _label(s, r, t, r in (12, 15))
    s["B4"] = "=Assumptions!B3"
    s["B5"] = "=Assumptions!B4"
    for k in range(1, 6):
        c, p, ac = cols[k], cols[k - 1], get_column_letter(1 + k)  # assumptions column
        s[f"{c}4"] = f"={p}4*(1+Assumptions!{ac}18)"
        s[f"{c}5"] = f"={c}4*Assumptions!{ac}19"
        s[f"{c}6"] = f"={c}4*Assumptions!$B$6"
        s[f"{c}7"] = f"={c}5-{c}6"
        s[f"{c}8"] = f"={c}7*Assumptions!$B$5"
        s[f"{c}9"] = f"={c}7-{c}8"
        s[f"{c}10"] = f"={c}4*Assumptions!$B$7"
        s[f"{c}11"] = f"=({c}4-{p}4)*Assumptions!$B$8"
        s[f"{c}12"] = f"={c}9+{c}6-{c}10-{c}11"
        s[f"{c}13"] = f"={c}3-0.5*Assumptions!$B$14"
        s[f"{c}14"] = f"=(1+Assumptions!$B$9)^(-{c}13)"
        s[f"{c}15"] = f"={c}12*{c}14"
    summary = [
        (18, "Sum of PV of FCFF", "=SUM(C15:G15)"),
        (19, "Terminal value (Gordon growth)",
         "=G12*(1+Assumptions!B10)/(Assumptions!B9-Assumptions!B10)"),
        (20, "PV of terminal value (Gordon)", "=B19/(1+Assumptions!B9)^(5-0.5*Assumptions!B14)"),
        (21, "Enterprise value (Gordon)", "=B18+B20"),
        (22, "Equity value (Gordon)", "=B21-Assumptions!B12"),
        (23, "Value per share (Gordon), Rs", "=B22/Assumptions!B13"),
        (25, "Terminal value (exit multiple)", "=G5*Assumptions!B11"),
        (26, "PV of terminal value (exit)", "=B25/(1+Assumptions!B9)^5"),
        (27, "Enterprise value (exit multiple)", "=B18+B26"),
        (28, "Equity value (exit multiple)", "=B27-Assumptions!B12"),
        (29, "Value per share (exit multiple), Rs", "=B28/Assumptions!B13"),
        (31, "Blended value per share, Rs", "=AVERAGE(B23,B29)"),
        (32, "Upside vs current price", "=B31/Assumptions!B15-1"),
    ]
    for r, lab, f in summary:
        _label(s, r, lab, r in (23, 29, 31))
        s[f"B{r}"] = f
    s["B32"].number_format = PCT
    for r in range(4, 13):
        for c in cols:
            s[f"{c}{r}"].number_format = NUM
    for c in cols:
        s[f"{c}14"].number_format = "0.0000"
        s[f"{c}15"].number_format = NUM
        s[f"{c}13"].number_format = "0.0"
    for r in (18, 19, 20, 21, 22, 25, 26, 27, 28):
        s[f"B{r}"].number_format = NUM
    for r in (23, 29, 31):
        s[f"B{r}"].number_format = "#,##0.00"
    s.column_dimensions["A"].width = 38
    for c in cols:
        s.column_dimensions[c].width = 13

    # ------------------------------------------------------------------ LBO
    b = wb.create_sheet("LBO")
    b["A1"] = "Leveraged buyout"
    b["A1"].font = Font(bold=True, size=13)
    entry = [
        (3, "Entry enterprise value", "=Assumptions!B22*Assumptions!B4"),
        (4, "Transaction fees", "=Assumptions!B28*B3"),
        (5, "Minimum cash funded", "=Assumptions!B29"),
        (6, "Total uses", "=B3+B4+B5"),
        (7, "Senior debt", "=Assumptions!B23*Assumptions!B4"),
        (8, "Mezzanine", "=Assumptions!B24*Assumptions!B4"),
        (9, "Sponsor equity (plug)", "=B6-B7-B8"),
        (10, "Check: sources - uses (should be 0)", "=B7+B8+B9-B6"),
    ]
    for r, lab, f in entry:
        _label(b, r, lab, r in (6, 9))
        b[f"B{r}"] = f
        b[f"B{r}"].number_format = NUM
    _label(b, 12, "Year", True)
    for k, c in enumerate(cols):
        b[f"{c}12"] = k
        b[f"{c}12"].font = BOLD
        b[f"{c}12"].fill = HEAD
    lab = {13: "Revenue", 14: "EBITDA", 15: "D&A", 16: "EBIT", 17: "Capex", 18: "Increase in NWC",
           20: "Senior debt, beginning", 21: "Senior interest", 22: "Mezzanine, beginning",
           23: "Mezzanine cash interest", 24: "Mezzanine PIK accrual", 25: "Cash taxes",
           26: "Cash flow before debt repayment", 27: "Mandatory amortisation",
           28: "Cash sweep", 29: "Senior debt, ending", 30: "Mezzanine, ending", 31: "Cash, ending"}
    for r, t in lab.items():
        _label(b, r, t, r in (26, 29, 30, 31))
    b["B13"] = "=DCF!B4"
    b["B14"] = "=DCF!B5"
    b["B29"] = "=B7"
    b["B30"] = "=B8"
    b["B31"] = "=B5"
    for k in range(1, 6):
        c, p = cols[k], cols[k - 1]
        b[f"{c}13"] = f"=DCF!{c}4"
        b[f"{c}14"] = f"=DCF!{c}5"
        b[f"{c}15"] = f"=DCF!{c}6"
        b[f"{c}16"] = f"=DCF!{c}7"
        b[f"{c}17"] = f"=DCF!{c}10"
        b[f"{c}18"] = f"=DCF!{c}11"
        b[f"{c}20"] = f"={p}29"
        b[f"{c}21"] = f"={c}20*Assumptions!$B$25"
        b[f"{c}22"] = f"={p}30"
        b[f"{c}23"] = f"={c}22*Assumptions!$B$26"
        b[f"{c}24"] = f"={c}22*Assumptions!$B$27"
        b[f"{c}25"] = f"=MAX(0,({c}16-{c}21-{c}23-{c}24)*Assumptions!$B$5)"
        b[f"{c}26"] = f"={c}14-{c}25-{c}17-{c}18-{c}21-{c}23"
        b[f"{c}27"] = f"=MIN({c}20,Assumptions!$B$30*$B$7)"
        b[f"{c}28"] = f"=MIN({c}20-{c}27,Assumptions!$B$31*MAX(0,{c}26-{c}27))"
        b[f"{c}29"] = f"={c}20-{c}27-{c}28"
        b[f"{c}30"] = f"={c}22+{c}24"
        b[f"{c}31"] = f"={p}31+{c}26-{c}27-{c}28"
    for r in list(range(13, 19)) + list(range(20, 32)):
        for c in cols:
            b[f"{c}{r}"].number_format = NUM
    exit_rows = [
        (34, "Hold period (years)", "=Assumptions!B33", "0"),
        (35, "Exit-year EBITDA", "=INDEX(C14:G14,B34)", NUM),
        (36, "Exit enterprise value", "=B35*Assumptions!B32", NUM),
        (37, "Net debt at exit", "=INDEX(C29:G29,B34)+INDEX(C30:G30,B34)-INDEX(C31:G31,B34)", NUM),
        (38, "Exit equity value", "=B36-B37", NUM),
        (39, "MOIC", "=B38/B9", '0.00"x"'),
        (40, "IRR", "=B39^(1/B34)-1", PCT),
        (42, "Attribution: EBITDA growth", "=Assumptions!B22*(B35-B14)", NUM),
        (43, "Attribution: multiple expansion", "=(Assumptions!B32-Assumptions!B22)*B35", NUM),
        (44, "Attribution: net debt paydown", "=(B7+B8-B5)-B37", NUM),
        (45, "Attribution: transaction fees", "=-B4", NUM),
        (46, "Attribution total", "=SUM(B42:B45)", NUM),
        (47, "Equity gain (exit equity - entry equity)", "=B38-B9", NUM),
        (48, "Check: attribution - gain (should be 0)", "=B46-B47", NUM),
    ]
    for r, t, f, fmt in exit_rows:
        _label(b, r, t, r in (39, 40))
        b[f"B{r}"] = f
        b[f"B{r}"].number_format = fmt
    b.column_dimensions["A"].width = 44
    for c in cols:
        b.column_dimensions[c].width = 13
    for ws in (a, s, b):
        ws.sheet_view.showGridLines = False
        for row in ws.iter_rows():
            for cell in row:
                if cell.column > 1:
                    cell.alignment = Alignment(horizontal="right")

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
