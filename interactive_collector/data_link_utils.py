"""
Extract and classify data-file links from HTML pages for batch download.

Used by the interactive collector to find PDF, CSV, ZIP, and similar download
links while skipping chrome in headers, footers, and navigation regions.
"""

from __future__ import annotations

import re
from typing import List, Set
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from utils.url_utils import infer_file_type, is_valid_url

# Extensions treated as downloadable data assets (not HTML landing pages).
DATA_FILE_EXTENSIONS: frozenset[str] = frozenset({
    "pdf",
    "csv",
    "tsv",
    "zip",
    "xlsx",
    "xls",
    "json",
    "xml",
    "txt",
    "rdf",
    "gz",
    "gzip",
    "tar",
    "7z",
    "parquet",
    "sas7bdat",
    "dta",
})

# Regions whose links are excluded (site chrome, not catalog content).
_EXCLUDE_SELECTORS: tuple[str, ...] = (
    "header",
    "footer",
    "nav",
    '[role="banner"]',
    '[role="navigation"]',
    '[role="contentinfo"]',
    "#header",
    "#footer",
    ".header",
    ".footer",
    ".site-header",
    ".site-footer",
    ".global-header",
    ".global-footer",
    ".cms-header",
    ".cms-footer",
    "#global-nav",
    ".skip-link",
    ".breadcrumb",
    ".breadcrumbs",
)

_MAIN_CONTENT_SELECTORS: tuple[str, ...] = (
    "main",
    '[role="main"]',
    "#main-content",
    "#content",
    ".region-content",
    "article",
)

_DATA_URL_RE = re.compile(
    r"\.(pdf|csv|tsv|zip|xlsx|xls|json|xml|txt|rdf|gz|tar|7z|parquet|sas7bdat|dta)(\?|#|$)",
    re.IGNORECASE,
)


def is_data_file_url(url: str) -> bool:
    """
    Return True if the URL likely points at a downloadable data file.

    Uses path extension via infer_file_type and a fallback regex on the full URL.
    """
    u = (url or "").strip()
    if not u or not is_valid_url(u):
        return False
    ft = infer_file_type(u)
    if ft in DATA_FILE_EXTENSIONS:
        return True
    return bool(_DATA_URL_RE.search(u))


def _remove_excluded_regions(soup: BeautifulSoup) -> None:
    """Remove header, footer, nav, and similar nodes from the parse tree."""
    for selector in _EXCLUDE_SELECTORS:
        for element in soup.select(selector):
            element.decompose()


def _main_content_root(soup: BeautifulSoup) -> BeautifulSoup | object:
    """Prefer main/article content; fall back to body or whole document."""
    for selector in _MAIN_CONTENT_SELECTORS:
        found = soup.select_one(selector)
        if found is not None:
            return found
    return soup.body if soup.body is not None else soup


def extract_data_links_from_html(html: str, page_url: str) -> List[str]:
    """
    Return sorted unique absolute URLs to data files linked from page content.

    Strips header/footer/nav regions, then collects ``a[href]`` from the main
    content area (or body if no main landmark exists).

    Args:
        html: Raw HTML of the catalog page.
        page_url: Page URL used to resolve relative hrefs.

    Returns:
        Sorted list of absolute data-file URLs.
    """
    if not (html or "").strip():
        return []
    soup = BeautifulSoup(html, "html.parser")
    _remove_excluded_regions(soup)
    root = _main_content_root(soup)
    found: Set[str] = set()
    for anchor in root.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if is_data_file_url(absolute):
            found.add(absolute.split("#")[0])
    return sorted(found)


def filter_urls_not_in_scoreboard(urls: List[str], scoreboard_urls: Set[str]) -> List[str]:
    """Drop URLs already present on the scoreboard (any entry type)."""
    if not scoreboard_urls:
        return list(urls)
    return [u for u in urls if u not in scoreboard_urls]
