# India Deal Lab

An end-to-end deal analysis tool for NSE-listed companies: **trading comps, DCF, LBO, football field and an auto-written investment committee (IC) memo**, plus a formula-live Excel export. Built as a Streamlit app in Python.

> Educational project. Not investment advice. Figures come from Yahoo Finance via `yfinance` or from bundled snapshots and can be incomplete or restated.

## What it does

| Tab | What you get |
|---|---|
| Summary | Headline cards (price, DCF value, comps value, LBO IRR), valuation range chart, key takeaways, company snapshot and data-quality notes |
| Valuation > Comps | Peer EV/EBITDA, EV/Sales, P/E with the subject company pinned; IQR outlier flags you can override with peer chips; implied value per share |
| Valuation > DCF | Driver-based 5-year FCFF, CAPM-based WACC, Gordon growth **and** exit-multiple terminal value, mid-year toggle, two sensitivity grids coloured against the current price |
| LBO | Sources and uses, senior and mezzanine tranches (cash and PIK), mandatory amortisation, cash sweep, IRR/MOIC, returns attribution, IRR grid highlighting cells that meet the hurdle, and "what must be true" solvers |
| Football field | Every method on one chart against current price and offer price |
| IC memo & export | Markdown memo with numbers pulled from the model, plus the formula-live Excel workbook |

## Case studies

Five preset NSE-listed, non-financial companies across paints, FMCG and electricals (banks and NBFCs are excluded because EV/EBITDA and free-cash-flow models do not suit lenders). Peer sets are defined in `deal_lab/universe.py`. A synthetic **Sample** mode lets the app run without any data connection; it is clearly labelled and never mixed with real data.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Run the tests:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Data handling

1. **Auto** mode tries live Yahoo Finance data first, then falls back to `data/snapshots/*.json`.
2. A weekly GitHub Action (`refresh-data.yml`) refreshes those snapshots and commits them.
3. Nothing is silently filled in. Missing fields produce visible warnings; incomplete peers are skipped and listed; every company input can be overridden in the sidebar.
4. Statements are fetched in INR and shown in Rs crore.

## Methodology

* **FCFF** = EBIT x (1 - tax) + D&A - capex - change in NWC. NWC change = NWC % x change in revenue.
* **WACC** = CAPM cost of equity (risk-free + beta x ERP + size premium) and after-tax cost of debt at a target debt weight. The risk-free rate, ERP and cost of debt are **placeholders**: update them before drawing conclusions.
* **Terminal value**: Gordon growth and exit multiple, with implied multiple / implied growth cross-checks. Mid-year option discounts flows at t - 0.5 and the Gordon TV at N - 0.5.
* **LBO**: cash-free/debt-free purchase; equity is the plug; interest on opening balances (no circularity); PIK accrues on mezzanine; cash tax floored at zero; no interim dividends, so IRR = MOIC^(1/n) - 1.
* **Attribution** splits equity gain into EBITDA growth, multiple expansion, net-debt paydown and fees, and sums exactly to the gain (tested).
* **Ability to pay**: bisection solver for the highest entry multiple that clears a target IRR with leverage held constant in turns of EBITDA.

## Tests

`tests/` covers the DCF against hand-computed closed forms, LBO sources = uses, debt-schedule roll-forward, cash reconciliation, attribution identity, IRR against `numpy-financial`, both solvers, the data parser (synthetic yfinance-shaped frames), and the Excel export (recalculated with LibreOffice and compared to the Python results), plus an end-to-end app smoke test.

## Deploy on Streamlit Community Cloud (free)

1. Push this repo to GitHub (see the commands below).
2. In the repo, open **Actions > Refresh data snapshots > Run workflow**. This fills `data/snapshots/`, which the
   app uses when Yahoo Finance blocks requests from Streamlit's servers. Wait for it to finish.
3. At share.streamlit.io choose **Create app**, select the repo, branch `main`, main file `app.py`, then **Deploy**.
4. Copy the app URL and add it as `APP_URL` (next section).

```bash
git init
git add .
git commit -m "Initial commit: India Deal Lab"
git branch -M main
git remote add origin https://github.com/<your-username>/india-deal-lab.git
git push -u origin main
```

### Keep the app awake

Community Cloud puts idle apps to sleep. `.github/workflows/keepalive.yml` opens the app in a headless browser every 6 hours and clicks the wake-up button if needed.

1. Repo **Settings > Secrets and variables > Actions > Variables tab**.
2. Add a repository variable named `APP_URL` with your app URL.
3. Run the workflow once from the **Actions** tab to confirm it succeeds.

The workflow skips itself until `APP_URL` is set. GitHub pauses scheduled workflows after 60 days without repository activity; the weekly snapshot-refresh commit counts as activity.

## Limitations

* Yahoo Finance coverage for Indian companies varies by company and year; the app flags gaps rather than hiding them.
* Indian rules restrict bank financing of share acquisitions, so the senior/mezzanine structure is a generic illustration, not a financeable deal structure.
* The Excel LBO uses a fixed 5-year horizon with the exit year chosen by the hold input.
* The IC memo is rule-based text over model output; it is not a substitute for diligence.
* No PDF export: download the memo as Markdown or print it from the browser.

## Project layout

```
app.py                     Streamlit UI
deal_lab/                  data, comps, dcf, lbo, football, memo, excel_export, universe
scripts/                   refresh_snapshots.py, keepalive.py
tests/                     pytest suite
data/snapshots/            bundled company snapshots (written by the weekly workflow)
.github/workflows/         tests, weekly data refresh, keep-alive
```
