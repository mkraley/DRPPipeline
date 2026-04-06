"""
Fetch the archived Data Refuge dataset listing (pages 1-21), insert
source_url and title into data_refuge.db (standard ``projects`` schema).

Page 1 uses the bare listing URL; pages 2-21 use ``?page=n`` on that URL.

Run from repo root:
    python scripts/scrape_data_refuge_datasets.py

Existing rows (same source_url) are left unchanged. Progress is printed to stderr.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from storage import Storage  # noqa: E402
from utils.Logger import Logger  # noqa: E402
from utils.url_utils import fetch_page_body  # noqa: E402

DEFAULT_LIST_URL = (
    "https://web.archive.org/web/20210316194219/https://www.datarefuge.org/dataset"
)
LISTING_PAGE_COUNT = 21
DB_PATH = REPO_ROOT / "data_refuge.db"


def listing_url(page: int) -> str:
    """CKAN listing URL for page 1..LISTING_PAGE_COUNT (page 1 has no query)."""
    if page < 1 or page > LISTING_PAGE_COUNT:
        raise ValueError(f"page must be 1..{LISTING_PAGE_COUNT}, got {page}")
    if page == 1:
        return DEFAULT_LIST_URL
    return f"{DEFAULT_LIST_URL}?page={page}"


def extract_datasets(html: str, base_url: str) -> list[tuple[str, str]]:
    """
    Parse dataset rows from listing HTML.

    Expects ``<ul class="dataset-list unstyled">`` with each ``<li>`` containing
    ``<h3><a href="...">title</a></h3>``.
    """
    soup = BeautifulSoup(html, "html.parser")
    ul = soup.find("ul", class_=lambda c: c and "dataset-list" in c)
    if ul is None:
        return []

    rows: list[tuple[str, str]] = []
    for li in ul.find_all("li", recursive=False):
        h3 = li.find("h3")
        if not h3:
            continue
        a = h3.find("a", href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        href = a["href"].strip()
        source_url = urljoin(base_url, href)
        rows.append((title, source_url))
    return rows


def populate_db(rows: list[tuple[str, str]]) -> tuple[int, int]:
    """
    Insert each (title, source_url) into ``projects`` if source_url is new.

    Returns:
        (inserted_count, skipped_existing_count)
    """
    inserted = 0
    skipped = 0
    for title, source_url in rows:
        if Storage.exists_by_source_url(source_url):
            skipped += 1
            continue
        drpid = Storage.create_record(source_url)
        Storage.update_record(drpid, {"title": title})
        inserted += 1
    return inserted, skipped


def main() -> None:
    Logger.initialize(log_level="WARNING")
    Storage.reset()
    Storage.initialize("StorageSQLLite", db_path=DB_PATH)

    total_inserted = 0
    total_skipped = 0

    for page in range(1, LISTING_PAGE_COUNT + 1):
        url = listing_url(page)
        status, body, content_type, _ = fetch_page_body(url)
        if status != 200 or not body:
            print(
                f"Failed to fetch listing page {page}: status={status}, "
                f"content_type={content_type!r}",
                file=sys.stderr,
            )
            sys.exit(1)

        rows = extract_datasets(body, url)
        inserted, skipped = populate_db(rows)
        total_inserted += inserted
        total_skipped += skipped
        print(
            f"Page {page}/{LISTING_PAGE_COUNT}: {len(rows)} scraped, "
            f"inserted {inserted}, skipped {skipped}",
            file=sys.stderr,
        )

    print(
        f"Database: {DB_PATH} - total inserted {total_inserted}, "
        f"skipped (already present) {total_skipped}.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
