#!/usr/bin/env python3
"""
Verify CmsGovCollector._extract_date_range against the live API.

Fetches real resource data for a CMS dataset and checks that time_start
and time_end are correctly inferred from dataset_version_date on Primary resources.

Usage (from repo root):
    python collectors/tools/test_cms_date_extraction.py
    python collectors/tools/test_cms_date_extraction.py --url https://data.cms.gov/...
"""

import argparse
import sys
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

_argv_backup = sys.argv[:]
sys.argv = [sys.argv[0], "cms_collector"]
from utils.Args import Args
from utils.Logger import Logger
from utils.url_utils import BROWSER_HEADERS
Args.initialize()
sys.argv = _argv_backup
Logger.initialize(log_level="WARNING")

from collectors.CmsGovCollector import CmsGovCollector

_API_BASE = "https://data.cms.gov/data-api/v1"


def fetch_resources_for_url(source_url: str) -> list[dict]:
    """Fetch all resources for a CMS dataset URL via the slug + dataset-type APIs."""
    path = source_url.split("data.cms.gov", 1)[-1]
    slug_url = f"{_API_BASE}/slug?path={quote(path)}"
    r = requests.get(slug_url, headers=BROWSER_HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json().get("data") or {}

    taxonomy_uuid = data.get("uuid")
    if not taxonomy_uuid:
        print(f"  ERROR: no uuid in slug response for {source_url}")
        return []

    res_url = f"{_API_BASE}/dataset-type/{taxonomy_uuid}/resources"
    r2 = requests.get(res_url, headers=BROWSER_HEADERS, timeout=30)
    r2.raise_for_status()
    return r2.json().get("data") or []


def check_url(source_url: str) -> bool:
    """Check date extraction for one URL. Returns True if time_start was found."""
    print(f"\nURL: {source_url}")
    resources = fetch_resources_for_url(source_url)

    primaries = [r for r in resources if r.get("type") == "Primary"]
    print(f"  {len(resources)} total resources, {len(primaries)} Primary")

    for r in primaries:
        print(f"    [{r.get('dataset_version_label','?')}]  "
              f"dataset_version_date={r.get('dataset_version_date')!r}  "
              f"name={r.get('file_name','')[:50]}")

    collector = CmsGovCollector()
    date_range = collector._extract_date_range(resources)
    print(f"  → time_start={date_range.get('time_start')!r}  "
          f"time_end={date_range.get('time_end')!r}")

    found = bool(date_range.get("time_start"))
    status = "OK" if found else "MISSING"
    print(f"  Status: {status}")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Test CMS date extraction")
    parser.add_argument(
        "--url",
        default="https://data.cms.gov/medicare-value-based-payment-modifier-program/value-modifier",
        help="CMS dataset URL to test (default: Value Modifier)",
    )
    args = parser.parse_args()

    ok = check_url(args.url)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
