"""
Debug script: fetch datalumos search page and save HTML to debug/.
Run to inspect actual response when checking for numFound.
"""

import sys
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

from utils.Args import Args
from utils.Logger import Logger
from duplicate_checking.datalumos_search import (
    _fetch_search_page,
    _parse_num_found,
    DATALUMOS_SEARCH_BASE,
)
from urllib.parse import urlencode

Args.initialize()
Logger.initialize(log_level="INFO")

_DEFAULT_PARAMS = {
    "start": "0",
    "ARCHIVE": "datalumos",
    "sort": "score desc,DATEUPDATED desc",
    "rows": "25",
}

url = "https://data.cdc.gov/Vision-Eye-Health/BRFSS-Vision-Module-Data-Vision-Eye-Health/pttf-ck53/about_data"
params = {**_DEFAULT_PARAMS, "q": url}
full_url = f"{DATALUMOS_SEARCH_BASE}?{urlencode(params)}"

print("Fetching", full_url[:80], "...")
html = None
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    try:
        page = browser.new_page()
        html = _fetch_search_page(full_url, 30_000, url, page)
    finally:
        browser.close()
if html is None:
    print("Fetch failed")
    sys.exit(1)

out = Path(__file__).parent / "datalumos_search_response.html"
out.write_text(html, encoding="utf-8")
print("Wrote", out)

n = _parse_num_found(html)
print("numFound:", n)

# Show snippet around "numFound" or "response"
if "numFound" in html:
    i = html.index("numFound")
    print("Snippet:", repr(html[max(0, i - 50) : i + 80]))
else:
    print("'numFound' not in response. Length:", len(html))
    print("First 500 chars:", repr(html[:500]))
