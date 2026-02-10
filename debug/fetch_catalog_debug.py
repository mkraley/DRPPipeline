"""
Debug script: fetch catalog.data.gov URL and inspect fetch_page_body result.
Run from repo root: python debug/fetch_catalog_debug.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.url_utils import fetch_page_body

URL = "https://catalog.data.gov/dataset/accessgudid-1f586"


def main() -> None:
    print("=== fetch_page_body result ===\n")
    status, body, content_type, is_logical_404 = fetch_page_body(URL)
    print(f"status={status}, content_type={content_type!r}, is_logical_404={is_logical_404}")
    print(f"body length: {len(body)}")
    print(f"First 400 chars of body:\n{body[:400]!r}")
    if body:
        replacement_count = body.count("\uFFFD")
        print(f"\nReplacement char (U+FFFD) count: {replacement_count}")

if __name__ == "__main__":
    main()
