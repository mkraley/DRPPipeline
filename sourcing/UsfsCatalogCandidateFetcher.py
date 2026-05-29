"""
Fetch candidate source URLs from the USFS Research Data Archive catalog.

Catalog listing: https://www.fs.usda.gov/rds/archive/catalog
"""

from __future__ import annotations

import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collectors.UsfsMetadataExtractor import AGENCY, OFFICE
from utils.url_utils import fetch_page_body

CATALOG_BASE = "https://www.fs.usda.gov/rds/archive/catalog"
DEFAULT_PAGE_SIZE = 10


def catalog_listing_url(page_index: int, page_size: int = DEFAULT_PAGE_SIZE) -> str:
    """Return the catalog listing URL for a 1-based page index."""
    if page_index < 1:
        raise ValueError(f"page_index must be >= 1, got {page_index}")
    params: list[str] = []
    if page_size != DEFAULT_PAGE_SIZE:
        params.append(f"pagesize={page_size}")
    if page_index > 1:
        params.append(f"pageIndex={page_index}")
    if not params:
        return CATALOG_BASE
    return f"{CATALOG_BASE}?{'&'.join(params)}"


def extract_catalog_entries(html: str, base_url: str = CATALOG_BASE) -> list[dict[str, str]]:
    """
    Parse catalog listing HTML into entry dicts with url and title.

    Expects ``<div class="document">`` blocks containing ``<h4><a href="...">title</a></h4>``.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str]] = []
    for doc in soup.find_all("div", class_="document"):
        h4 = doc.find("h4")
        if not h4:
            continue
        link = h4.find("a", href=True)
        if not link:
            continue
        title = link.get_text(strip=True)
        if not title:
            continue
        href = link["href"].strip()
        source_url = urljoin(base_url, href)
        rows.append({"url": source_url, "title": title})
    return rows


def _entry_dict(url: str, title: str) -> dict[str, str]:
    return {"url": url, "title": title, "agency": AGENCY, "office": OFFICE}


def fetch_catalog_page(
    page_index: int,
    *,
    timeout: int = 60,
    max_retries: int = 3,
) -> tuple[list[dict[str, str]], int]:
    """
    Fetch one catalog listing page with retries.

    Returns:
        Tuple of (candidate rows for the page, final HTTP status).
        On success, status is 200 and rows may be empty when the catalog ends.
    """
    url = catalog_listing_url(page_index)
    last_status = -1

    for attempt in range(max_retries):
        status, body, _content_type, _logical_404 = fetch_page_body(url, timeout=timeout)
        last_status = status
        if status == 200 and body:
            page_rows = extract_catalog_entries(body, url)
            return (
                [_entry_dict(e["url"], e["title"]) for e in page_rows],
                status,
            )
        if attempt < max_retries - 1:
            time.sleep(2**attempt)

    return [], last_status


class UsfsCatalogCandidateFetcher:
    """Enumerate USFS Research Data Archive catalog entries."""

    def get_candidate_urls(self, limit: int | None = None) -> tuple[list[dict[str, str]], int]:
        """
        Walk catalog listing pages and return entry metadata.

        Each dict has keys: url, title, agency, office.

        Args:
            limit: Max entries to return. None = all catalog entries.

        Returns:
            Tuple of (candidate rows, skipped_count). skipped_count is always 0 here.

        Raises:
            RuntimeError: If a catalog page cannot be fetched after retries.
        """
        rows: list[dict[str, str]] = []
        page_index = 1

        while True:
            if limit is not None and len(rows) >= limit:
                break

            page_rows, status = fetch_catalog_page(page_index)
            if status != 200:
                raise RuntimeError(
                    f"Failed to fetch USFS catalog page {page_index}: status={status}"
                )
            if not page_rows:
                break

            for entry in page_rows:
                if limit is not None and len(rows) >= limit:
                    break
                rows.append(entry)

            if len(page_rows) < DEFAULT_PAGE_SIZE:
                break
            page_index += 1

        return rows, 0
