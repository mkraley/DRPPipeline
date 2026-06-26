"""
HTTP client for Ag Data Commons (ADC) metadata via the public Figshare API.

Ag Data Commons runs on Figshare; article metadata and hosted files are available
without authentication at https://api.figshare.com/v2.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from utils.Logger import Logger

FIGSHARE_API_BASE = "https://api.figshare.com/v2"
FIGSHARE_SEARCH_TERM = "USDA.ADC"
ADC_PORTAL_OAI_SET = "portal_1059"
ADC_HOST = "agdatacommons.nal.usda.gov"
OAI_NS = {"oai": "http://www.openarchives.org/OAI/2.0/"}
DEFAULT_PAGE_SIZE = 100
DEFAULT_HEADERS = {"User-Agent": "DRPPipeline/1.0"}


def article_id_from_source_url(url: str) -> int | None:
    """
    Extract the Figshare article ID from an Ag Data Commons portal URL.

    Args:
        url: ADC dataset page URL ending in a numeric article ID.

    Returns:
        Figshare article ID, or None when the URL does not contain one.
    """
    last_segment = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    if last_segment.isdigit():
        return int(last_segment)
    return None


class AdcApiClient:
    """Fetch ADC dataset listings and article metadata from Figshare."""

    def __init__(self, *, request_delay: float = 0.15) -> None:
        """
        Initialize the API client.

        Args:
            request_delay: Seconds to sleep between paginated search requests.
        """
        self._request_delay = request_delay

    def search_adc_article_summaries(
        self,
        *,
        page: int,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        """
        Return one page of Figshare search hits for the USDA.ADC DOI prefix.

        Args:
            page: 1-based page number.
            page_size: Results per page (max 100).

        Returns:
            Raw Figshare article summary dicts from the search endpoint.
        """
        response = requests.post(
            f"{FIGSHARE_API_BASE}/articles/search",
            json={"search_for": FIGSHARE_SEARCH_TERM, "page_size": page_size, "page": page},
            headers=DEFAULT_HEADERS,
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return []
        return payload

    def list_adc_article_ids(
        self,
        *,
        max_pages: int | None = None,
        limit: int | None = None,
    ) -> list[int]:
        """
        Enumerate ADC article IDs via USDA.ADC Figshare search.

        Args:
            max_pages: Optional cap on search pages (for testing).
            limit: Stop once this many ADC article IDs have been collected.

        Returns:
            Sorted unique Figshare article IDs whose public HTML URL is on ADC.
        """
        article_ids: list[int] = []
        seen: set[int] = set()
        page = 1
        while max_pages is None or page <= max_pages:
            batch = self.search_adc_article_summaries(page=page)
            if not batch:
                break
            for item in batch:
                article_id = self._adc_article_id_from_summary(item)
                if article_id is not None and article_id not in seen:
                    seen.add(article_id)
                    article_ids.append(article_id)
                    if limit is not None and len(article_ids) >= limit:
                        return sorted(article_ids)
            if len(batch) < DEFAULT_PAGE_SIZE:
                break
            page += 1
            if self._request_delay > 0:
                time.sleep(self._request_delay)
        return sorted(article_ids)

    def harvest_portal_article_ids(
        self,
        *,
        max_pages: int | None = None,
        on_page: Callable[[int, int], None] | None = None,
    ) -> list[int]:
        """
        Enumerate article IDs from the ARC Figshare OAI portal set.

        Args:
            max_pages: Optional cap on OAI pages (for testing).
            on_page: Optional callback ``(page_number, ids_so_far)`` after each page.

        Returns:
            Sorted unique article IDs from ``portal_1059``.
        """
        article_ids: list[int] = []
        seen: set[int] = set()
        token: str | None = None
        pages = 0
        while max_pages is None or pages < max_pages:
            if token:
                params: dict[str, str] = {"verb": "ListIdentifiers", "resumptionToken": token}
            else:
                params = {
                    "verb": "ListIdentifiers",
                    "metadataPrefix": "oai_dc",
                    "set": ADC_PORTAL_OAI_SET,
                }
            response = requests.get(
                f"{FIGSHARE_API_BASE}/oai",
                params=params,
                headers=DEFAULT_HEADERS,
                timeout=120,
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
            error = root.find(".//oai:error", OAI_NS)
            if error is not None:
                raise RuntimeError(
                    f"Figshare OAI error: {error.get('code')} {error.text or ''}".strip()
                )
            for node in root.findall(".//oai:identifier", OAI_NS):
                text = node.text or ""
                if text.startswith("oai:figshare.com:article/"):
                    article_id = int(text.rsplit("/", 1)[-1])
                    if article_id not in seen:
                        seen.add(article_id)
                        article_ids.append(article_id)
            resumption = root.find(".//oai:resumptionToken", OAI_NS)
            token = resumption.text if resumption is not None and resumption.text else None
            pages += 1
            if on_page is not None:
                on_page(pages, len(article_ids))
            if not token:
                break
            if self._request_delay > 0:
                time.sleep(self._request_delay)
        return sorted(article_ids)

    def fetch_article(self, article_id: int) -> dict[str, Any]:
        """
        Fetch full metadata for one Figshare article.

        Args:
            article_id: Figshare article ID.

        Returns:
            Article JSON document from Figshare.
        """
        response = requests.get(
            f"{FIGSHARE_API_BASE}/articles/{article_id}",
            headers=DEFAULT_HEADERS,
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected article payload for {article_id}")
        return payload

    def merge_article_ids(
        self,
        *,
        search_max_pages: int | None = None,
        oai_max_pages: int | None = None,
        limit: int | None = None,
    ) -> list[int]:
        """
        Union article IDs from USDA.ADC search and the ADC OAI portal set.

        When ``limit`` is set, only the Figshare search is used (fast path for
        ``--num-rows`` sampling). A full run with no limit also harvests OAI
        ``portal_1059`` for externally linked catalog records.

        Returns:
            Sorted unique Figshare article IDs for ADC-hosted public items.
        """
        if limit is not None:
            Logger.info(
                "ADC enumeration: Figshare USDA.ADC search (limit=%s, OAI skipped)",
                limit,
            )
            return self.list_adc_article_ids(max_pages=search_max_pages, limit=limit)

        Logger.info("ADC enumeration: Figshare USDA.ADC search (full catalog)")
        search_ids = self.list_adc_article_ids(max_pages=search_max_pages)
        Logger.info(
            "ADC enumeration: USDA.ADC search found %s IDs; harvesting OAI portal_1059",
            len(search_ids),
        )

        def _log_oai_page(page_number: int, ids_so_far: int) -> None:
            if page_number == 1 or page_number % 25 == 0:
                Logger.info(
                    "ADC OAI harvest: page %s, %s article IDs collected so far",
                    page_number,
                    ids_so_far,
                )

        oai_ids = self.harvest_portal_article_ids(
            max_pages=oai_max_pages,
            on_page=_log_oai_page,
        )
        merged = sorted(set(search_ids) | set(oai_ids))
        Logger.info(
            "ADC enumeration complete: %s from search, %s from OAI, %s unique total",
            len(search_ids),
            len(oai_ids),
            len(merged),
        )
        return merged

    def _adc_article_id_from_summary(self, item: dict[str, Any]) -> int | None:
        """Return article ID when the search hit is an Ag Data Commons portal page."""
        public_url = str(item.get("url_public_html") or "")
        if ADC_HOST not in public_url:
            return None
        article_id = item.get("id")
        if article_id is None:
            return None
        return int(article_id)
