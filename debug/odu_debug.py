"""
Debug script: test ODU extraction via Playwright.
Run to verify _extract_original_distribution_url_from_page against sample HTML.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.Args import Args
from utils.Logger import Logger
from playwright.sync_api import sync_playwright
from duplicate_checking.datalumos_search import _extract_original_distribution_url_from_page

Args.initialize()
Logger.initialize(log_level="WARNING")

html = """<div><label>Original Distribution URL:</label>
<a href="https://data.cdc.gov/x/y">https://data.cdc.gov/x/y</a></div>"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    try:
        page = browser.new_page()
        page.set_content(html)
        odu = _extract_original_distribution_url_from_page(page)
        print("ODU:", repr(odu))
    finally:
        browser.close()
