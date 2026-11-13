"""Wake a sleeping Streamlit Community Cloud app and confirm it renders.

Streamlit puts apps to sleep after a period with no visitors, and only a real browser
session (a websocket connection) counts as traffic, so this uses a headless Chromium.

Usage:  APP_URL=https://your-app.streamlit.app python scripts/keepalive.py
Exit code 0 = app is up and rendering; 1 = could not confirm.
"""
from __future__ import annotations

import os
import re
import sys
import time

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

MARKER = "India Deal Lab"  # text that the app title renders


def main() -> int:
    url = os.environ.get("APP_URL", "").strip()
    if not url.startswith("http"):
        print("APP_URL is not set to a full https:// URL.")
        return 1

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            except Exception as exc:  # DNS failure, refused connection, timeout
                print(f"FAILED: could not open {url} ({type(exc).__name__}).")
                return 1

            wake = page.get_by_role("button", name=re.compile("get this app back up", re.I))
            try:
                wake.wait_for(state="visible", timeout=15_000)
                wake.click()
                print("App was asleep: clicked the wake-up button.")
            except PWTimeout:
                print("No wake-up button shown (app already awake or still loading).")

            # Streamlit Cloud renders the app inside an iframe; elsewhere it is the top page.
            # Poll both so neither path has to time out before the other is tried.
            frame = page.frame_locator('iframe[title="streamlitApp"]')
            deadline = time.time() + 180
            while time.time() < deadline:
                for where, loc in (("Streamlit frame", frame.get_by_text(MARKER)),
                                   ("top-level page", page.get_by_text(MARKER))):
                    try:
                        if loc.first.is_visible(timeout=1_000):
                            print(f"OK: app rendered on the {where}.")
                            return 0
                    except PWTimeout:
                        pass
                time.sleep(2)
            print("FAILED: app title never appeared. Check the app in a browser.")
            return 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
