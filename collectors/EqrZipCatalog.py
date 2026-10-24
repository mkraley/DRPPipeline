"""Open the EQR viewer and read the quarterly CSV zip links."""

from __future__ import annotations

from collectors.EqrProjectRange import VIEWER_URL
from collectors.EqrZipLink import EqrZipLink, csv_links_from_pairs


class EqrZipCatalog:
    """Load ``CSV_YYYY_Q#.zip`` links from the viewer's Downloads tab."""

    def list_links(self) -> list[EqrZipLink]:
        """
        Click Downloads and return the CSV zip links.

        The quarterly table is empty until that tab is opened, and each href
        carries a path token that later downloads have to refresh.

        Returns:
            CSV zips in chronological order. XML zips are omitted.
        """
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                pairs = _anchor_pairs(page)
            finally:
                browser.close()
        return csv_links_from_pairs(pairs)


def _anchor_pairs(page: object) -> list[tuple[str, str]]:
    """Return anchor text and href after the Downloads tab has loaded."""
    page.goto(VIEWER_URL, timeout=90000, wait_until="domcontentloaded")  # type: ignore[attr-defined]
    page.get_by_text("Downloads", exact=True).click()  # type: ignore[attr-defined]
    page.wait_for_selector("a[href*='/CSV/CSV_']", timeout=30000)  # type: ignore[attr-defined]
    pairs: list[tuple[str, str]] = []
    for anchor in page.locator("a").all():  # type: ignore[attr-defined]
        text = " ".join(anchor.inner_text().split())
        href = anchor.get_attribute("href") or ""
        pairs.append((text, href))
    return pairs
