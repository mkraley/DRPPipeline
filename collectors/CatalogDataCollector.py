"""
Catalog Data Collector for DRP Pipeline.

NOTE: not fully implemented, and not used in the current pipeline, but may be useful for future reference.

Collects data from catalog.data.gov dataset pages:
- Validates and accesses source_url (source page)
- Locates "Downloads & Resources" section
- Follows each download link, records file type and title for non-404s
- Writes results to status_notes (no PDF, dataset download, or metadata)
"""

from __future__ import annotations

from typing import Any

from collectors.CollectorBase import CollectorBase
from collectors.PlaywrightSession import PlaywrightSession
from collectors.collector_url import validate_and_access_url
from storage import Storage
from utils.Errors import record_error
from utils.Logger import Logger
from utils.url_utils import fetch_page_body, fetch_url_head, infer_file_type


class CatalogDataCollector(CollectorBase):
    """
    Collector for catalog.data.gov dataset pages.

    Extracts download resource links from the "Downloads & Resources" section,
    follows each link, and records file type and title for non-404 responses.
    """

    _storage_status_mode = "notes_only"
    _DOWNLOADS_SECTION_HEADING = "Downloads & Resources"

    def __init__(self, headless: bool = True) -> None:
        """
        Initialize CatalogDataCollector.

        Args:
            headless: If False, run browser in visible mode for debugging.
        """
        self._headless = headless
        self._session = PlaywrightSession(
            headless=headless,
            slow_mo=500 if not headless else 0,
        )
        self._drpid = 0
        self._result: dict[str, Any] = {}

    @property
    def _page(self):
        """Default Playwright page (used by tests)."""
        return self._session.page

    def apply_result_to_storage(self, drpid: int, result: dict[str, Any]) -> None:
        """
        Merge notes-only results without setting a collected status.

        Args:
            drpid: Project DRPID.
            result: Collection fields keyed by Storage column names.
        """
        update_fields = {key: value for key, value in result.items() if value is not None}
        if update_fields:
            Storage.update_record(drpid, update_fields)

    def _collect(
        self,
        url: str,
        drpid: int,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Collect download resource info from a catalog.data.gov source page.

        Args:
            url: Source URL (catalog.data.gov dataset page).
            drpid: DRPID for the record.
            record: Full Storage record (unused).

        Returns:
            Dict with status_notes for Storage update.
        """
        self._drpid = drpid
        self._result = {}

        if not validate_and_access_url(drpid, url):
            return self._result

        try:
            if not self._init_browser_and_load_page(url):
                return self._result

            links = self._extract_download_links()
            if links is None:
                return self._result

            if not links:
                record_error(drpid, "Downloads & Resources section has no links")
                return self._result

            resources = self._follow_links_and_collect_resources(links)
            if resources is None:
                return self._result

            status_notes = self._format_status_notes(resources)
            self._result["status_notes"] = status_notes
            Logger.info("Downloads & Resources:%s", status_notes)
        finally:
            self._session.close()

        return self._result

    def _init_browser_and_load_page(self, url: str) -> bool:
        """
        Initialize Playwright browser and load the source page.

        Args:
            url: URL to load.

        Returns:
            True if successful, False otherwise.
        """
        if not self._session.start():
            record_error(self._drpid, "Failed to initialize browser")
            return False

        if not self._session.goto(url):
            record_error(self._drpid, f"Failed to load page: {url}")
            return False

        page = self._session.page
        if page is not None:
            page.wait_for_timeout(500)
        return True

    def _extract_download_links(self) -> list[tuple[str, str]] | None:
        """
        Find "Downloads & Resources" h3, its sibling ul, and extract (href, text) from li>a.

        Returns:
            List of (href, link_text) tuples, or None if section not found.
        """
        script = """
        () => {
            function getDirectText(el) {
                let t = '';
                for (let i = 0; i < el.childNodes.length; i++) {
                    if (el.childNodes[i].nodeType === 3)
                        t += el.childNodes[i].textContent;
                }
                return t.trim().replace(/\\s+/g, ' ');
            }
            const h3s = document.querySelectorAll('h3');
            const h3 = Array.from(h3s).find(h =>
                h.textContent && h.textContent.trim() === 'Downloads & Resources'
            );
            if (!h3) return null;
            const ul = h3.nextElementSibling;
            if (!ul || ul.tagName !== 'UL') return null;
            const links = [];
            ul.querySelectorAll('li a').forEach(a => {
                if (a.href) {
                    links.push({
                        href: a.href,
                        text: getDirectText(a)
                    });
                }
            });
            return links;
        }
        """
        page = self._session.page
        if page is None:
            return None
        result = page.evaluate(script)
        if result is None:
            record_error(
                self._drpid,
                "Source page missing '<h3>Downloads & Resources</h3>' or sibling <ul>",
            )
            return None
        raw_links = [(item["href"], item["text"]) for item in result]
        return self._dedupe_links(raw_links)

    def _dedupe_links(self, links: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """
        Remove duplicate links by href (first occurrence wins).

        Args:
            links: List of (href, text) tuples.

        Returns:
            Deduplicated list preserving order.
        """
        seen: set[str] = set()
        deduped: list[tuple[str, str]] = []
        for href, text in links:
            if href not in seen:
                seen.add(href)
                deduped.append((href, text))
        return deduped

    def _resolve_catalog_resource_page(
        self, catalog_url: str
    ) -> tuple[str, str | None] | None:
        """
        Turn a catalog.data.gov resource page URL into the real download URL.

        Args:
            catalog_url: URL of catalog.data.gov resource page.

        Returns:
            (actual_download_url, data_format) or None if #res_url not found.
        """
        status_code, _body, _content_type, is_logical_404 = fetch_page_body(catalog_url)
        if status_code == 404 or is_logical_404:
            return None
        page = self._session.page
        if page is None:
            return None
        try:
            page.goto(catalog_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(300)
        except Exception:
            return None

        script = """
        () => {
            const a = document.getElementById('res_url');
            if (!a || !a.href) return null;
            return {
                href: a.href,
                dataFormat: a.getAttribute('data-format') || null
            };
        }
        """
        result = page.evaluate(script)
        if result is None:
            return None
        data_format = result.get("dataFormat")
        if data_format:
            data_format = str(data_format).lower().strip()
        return (result["href"], data_format)

    def _follow_links_and_collect_resources(
        self, links: list[tuple[str, str]]
    ) -> list[tuple[str, str, str]] | None:
        """
        Follow each link with HEAD request; record (title, result) for all links.

        Args:
            links: List of (href, link_text) from _extract_download_links.

        Returns:
            List of (title, result, url) for all links, or None if all 404.
        """
        entries: list[tuple[str, str, str]] = []
        has_success = False
        hrefs = [href for href, _ in links]
        for href, title in links:
            title_clean = title.strip() or "(no title)"
            actual_url = href
            data_format: str | None = None

            if href.startswith("https://catalog.data.gov"):
                resolved = self._resolve_catalog_resource_page(href)
                if resolved is None:
                    entries.append((title_clean, "404", ""))
                    continue
                actual_url, data_format = resolved
                if actual_url in hrefs:
                    continue

            status_code, content_type, _error_msg = fetch_url_head(actual_url)
            if status_code == 404 or status_code < 0:
                entries.append((title_clean, "404", ""))
            else:
                file_type = (
                    data_format
                    if data_format
                    else infer_file_type(actual_url, content_type)
                )
                entries.append((title_clean, file_type, actual_url))
                has_success = True

        if not has_success:
            record_error(self._drpid, "All download links returned 404")
            return None
        return entries

    def _format_status_notes(self, entries: list[tuple[str, str, str]]) -> str:
        """Format resource list for status_notes (title -> result, with URL for success)."""
        lines = []
        for title, result, url in entries:
            line = f"  {title} -> {result}"
            if url:
                line += f" {url}"
            lines.append(line)
        return "\n" + "\n".join(lines)
