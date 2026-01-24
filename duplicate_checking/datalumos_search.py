"""
Datalumos search via the public search/studies endpoint.

The datalumos search page uses a GET request with query params. The response
embeds JSON (React props) including "numFound" and "docs" (with IDs). We use
Playwright to load the page, then optionally navigate to each result and verify
"Original Distribution URL:" matches the search URL.
"""

import re
from urllib.parse import urlencode

from playwright.sync_api import Page, sync_playwright

from utils.Logger import Logger

DATALUMOS_SEARCH_BASE = "https://www.datalumos.org/datalumos/search/studies"
DATALUMOS_PROJECT_URL = "https://www.datalumos.org/datalumos/project/{project_id}/version/V1/view"

_DEFAULT_PARAMS = {
    "start": "0",
    "ARCHIVE": "datalumos",
    "sort": "score desc,DATEUPDATED desc",
    "rows": "25",
}

_NUMFOUND_RE = re.compile(r'"numFound"\s*:\s*(\d+)')
_ID_RE = re.compile(r'"ID"\s*:\s*(\d+)')


def _parse_num_found(text: str) -> int:
    """Extract numFound from response text. Returns -1 if not found."""
    m = _NUMFOUND_RE.search(text)
    return int(m.group(1)) if m else -1


def _parse_result_ids(text: str) -> list[int]:
    """Extract study IDs from search response docs. Returns empty list if none."""
    return [int(g) for g in _ID_RE.findall(text)]


def _parse_and_validate_search_response(text: str, source_url: str) -> int | None:
    """
    Parse numFound from search HTML, log Cloudflare / missing / multi-match
    warnings as needed, and return num (>= 0) on success or None on failure.
    """
    num = _parse_num_found(text)
    if num < 0:
        if "Just a moment" in text:
            Logger.warning(
                f"Cloudflare challenge detected; datalumos search could not complete for {source_url!r}"
            )
        else:
            Logger.warning(
                f"Datalumos search response missing 'numFound' for {source_url!r}"
            )
        return None
    if num > 1:
        Logger.warning(
            f"Datalumos returned {num} matches for {source_url!r}; expected at most one"
        )
    return num


_ODU_EXTRACT_JS = """
() => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
  let n;
  while (n = walker.nextNode()) {
    if (/Original\\s+Distribution\\s+URL\\s*:?\\s*/.test(n.textContent)) {
      let el = n.parentElement;
      while (el) {
        const candidates = el.tagName === 'A' ? [el] : el.querySelectorAll('a');
        for (const a of candidates) {
          const t = (a.textContent || '').trim();
          if (t && /^https?:\\/\\//i.test(t)) return t;
        }
        el = el.nextElementSibling;
      }
      return null;
    }
  }
  return null;
}
"""


def _extract_original_distribution_url_from_page(page: Page) -> str | None:
    """
    Find the field labelled "Original Distribution URL:" on the current page
    and return the stripped text of the adjacent <a> element, or None if not found.
    Uses Playwright page.evaluate() to run DOM traversal in the browser.
    """
    result = page.evaluate(_ODU_EXTRACT_JS)
    return result if isinstance(result, str) and result else None


def _fetch_search_page(
    url: str,
    timeout_ms: int,
    source_url: str,
    page: Page,
) -> str | None:
    """
    Load the search page in the given Playwright page and return its HTML.

    Caller owns the Playwright session. On any exception, log a warning
    (using source_url) and return None.
    """
    try:
        page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        return page.content()
    except Exception as e:
        Logger.warning(f"Datalumos search request failed for {source_url!r}: {e}")
        return None


def _check_result_pages_for_odu_match(
    page: Page,
    result_urls: list[str],
    expected: str,
    source_url: str,
    timeout_ms: int,
) -> bool:
    """
    Navigate to each result URL, extract Original Distribution URL, and return
    True if any matches `expected`. Log warnings on goto failures or when no
    match is found.
    """
    found: list[tuple[str, str]] = []
    for result_url in result_urls:
        try:
            page.goto(
                result_url,
                timeout=timeout_ms,
                wait_until="domcontentloaded",
            )
            html = page.content()
            if "Just a moment" in html or "Just a minute" in html:
                Logger.warning(
                    f"Cloudflare challenge detected on result page {result_url}; "
                    f"could not extract Original Distribution URL"
                )
                continue
            odu = _extract_original_distribution_url_from_page(page)
        except Exception as e:
            Logger.warning(
                f"Failed to load datalumos result page {result_url}: {e}"
            )
            continue
        if odu is None:
            continue
        if odu == expected:
            return True
        found.append((result_url, odu))
    if found:
        parts = [f"{u}: {o!r}" for u, o in found]
        Logger.warning(
            f"Searched for {source_url!r}; no matching Original Distribution URL. "
            f"Result(s) found: {'; '.join(parts)}"
        )
    else:
        Logger.warning(
            f"Searched for {source_url!r}; navigated to {len(result_urls)} result(s) "
            f"but could not extract Original Distribution URL from any"
        )
    return False


def search_datalumos(
    source_url: str,
    *,
    timeout: float = 30.0,
    headless: bool = False,
) -> int:
    """
    Search datalumos for the given source_url.

    Uses Playwright to load the search/studies page with q=source_url,
    then parses the embedded JSON to obtain numFound.

    Args:
        source_url: The URL to search for (e.g. a data.cdc.gov about_data link).
        timeout: Navigation timeout in seconds.
        headless: If False, use a visible browser (can help with Cloudflare).

    Returns:
        The number of matching studies (numFound). -1 on network/parse error.
    """
    params = {**_DEFAULT_PARAMS, "q": source_url}
    url = f"{DATALUMOS_SEARCH_BASE}?{urlencode(params)}"
    timeout_ms = int(timeout * 1000)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                page = browser.new_page()
                text = _fetch_search_page(url, timeout_ms, source_url, page)
            finally:
                browser.close()
    except Exception as e:
        Logger.warning(f"Datalumos search request failed for {source_url!r}: {e}")
        return -1

    if text is None:
        return -1
    num = _parse_and_validate_search_response(text, source_url)
    if num is None:
        return -1
    return num


def verify_source_url_in_datalumos(
    source_url: str,
    *,
    timeout: float = 30.0,
    headless: bool = False,
) -> bool:
    """
    Search datalumos for source_url, navigate to each result, and return True
    only if some result's "Original Distribution URL:" <a> text (stripped)
    equals the search URL.

    - If navigating to a result URL fails, log a warning and continue.
    - If no result has a matching ODU, log a warning comparing expected vs found
      and return False.

    headless=False can help avoid Cloudflare blocking (use for live verification).
    """
    params = {**_DEFAULT_PARAMS, "q": source_url}
    search_url = f"{DATALUMOS_SEARCH_BASE}?{urlencode(params)}"
    timeout_ms = int(timeout * 1000)
    expected = source_url.strip()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                page = browser.new_page()
                text = _fetch_search_page(
                    search_url, timeout_ms, source_url, page
                )
                if text is None:
                    return False
                num = _parse_and_validate_search_response(text, source_url)
                if num is None:
                    return False
                ids = _parse_result_ids(text)
                if not ids:
                    Logger.warning(
                        f"Datalumos reported {num} match(es) for {source_url!r} "
                        f"but no result IDs could be parsed"
                    )
                    return False
                result_urls = [
                    DATALUMOS_PROJECT_URL.format(project_id=i) for i in ids
                ]
                return _check_result_pages_for_odu_match(
                    page, result_urls, expected, source_url, timeout_ms
                )
            finally:
                browser.close()
    except Exception as e:
        Logger.warning(f"Datalumos verification failed for {source_url!r}: {e}")
        return False
