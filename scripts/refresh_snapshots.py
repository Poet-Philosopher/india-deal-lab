"""Refresh bundled snapshots for every ticker in the preset universe.

Run locally or from the weekly GitHub Action:  python scripts/refresh_snapshots.py

* Existing snapshots are kept when a refresh fails, so a flaky run never deletes data.
* Exit code is non-zero only if NOTHING could be refreshed.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deal_lab.data import fetch_live, save_snapshot  # noqa: E402
from deal_lab.universe import all_tickers  # noqa: E402

RETRIES = 3


def main() -> int:
    ok, failed = [], []
    for ticker in all_tickers():
        cd = None
        for attempt in range(1, RETRIES + 1):
            try:
                cd = fetch_live(ticker)
                break
            except Exception as exc:
                print(f"  {ticker}: attempt {attempt} failed ({exc})")
                time.sleep(2 * attempt)
        if cd is None or not cd.is_complete():
            reason = "fetch failed" if cd is None else "incomplete data: " + "; ".join(cd.warnings)
            print(f"SKIP {ticker}: {reason}")
            failed.append(ticker)
            continue
        path = save_snapshot(cd)
        print(f"OK   {ticker}: {cd.name} -> {path.name}")
        ok.append(ticker)
        time.sleep(1)  # be polite to the data provider
    print(f"\nRefreshed {len(ok)}, skipped {len(failed)}: {failed}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
