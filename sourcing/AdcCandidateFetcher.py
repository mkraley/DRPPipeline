"""
Fetch candidate source URLs from the USDA Ag Data Commons (ADC) Figshare portal.

Enumerates datasets via the public Figshare API (USDA.ADC search plus the ARC
OAI portal set ``portal_1059``). File inventories use Figshare metadata and,
when needed, Dryad/Zenodo APIs for externally hosted harvest records.
"""

from __future__ import annotations

from typing import Any

from sourcing.AdcApiClient import AdcApiClient
from sourcing.AdcFileInventory import AdcFileInventory

AGENCY = "US Department of Agriculture"
OFFICE = "National Agricultural Library"


class AdcCandidateFetcher:
    """Enumerate ADC datasets and optional file inventories."""

    def __init__(
        self,
        *,
        api_client: AdcApiClient | None = None,
        inventory: AdcFileInventory | None = None,
    ) -> None:
        """
        Initialize the fetcher.

        Args:
            api_client: Figshare API client (created when omitted).
            inventory: File inventory helper (created when omitted).
        """
        self._api = api_client or AdcApiClient()
        self._inventory = inventory or AdcFileInventory()

    def get_candidate_urls(self, limit: int | None = None) -> tuple[list[dict[str, str]], int]:
        """
        Return ADC dataset portal URLs with agency/office metadata.

        Args:
            limit: Max datasets to return. None = all discovered IDs.

        Returns:
            Tuple of (candidate rows, skipped_count). skipped_count is always 0.
        """
        article_ids = self._api.merge_article_ids(limit=limit)
        rows: list[dict[str, str]] = []
        for article_id in article_ids:
            article = self._api.fetch_article(article_id)
            row = self.build_candidate_row(article)
            if row:
                rows.append(row)
        return rows, 0

    def build_candidate_row(
        self,
        article: dict[str, Any],
        *,
        include_inventory: bool = False,
    ) -> dict[str, str] | None:
        """
        Convert a Figshare article document to a sourcing candidate row.

        Args:
            article: Full Figshare article JSON.
            include_inventory: When True, populate file summary fields (not status_notes).

        Returns:
            Candidate dict or None when the article is not on the ADC portal.
        """
        source_url = str(article.get("url_public_html") or "")
        if "agdatacommons.nal.usda.gov" not in source_url:
            return None
        row: dict[str, str] = {
            "url": source_url,
            "title": str(article.get("title") or ""),
            "agency": AGENCY,
            "office": OFFICE,
            "article_id": str(article.get("id") or ""),
        }
        if not include_inventory:
            return row
        files = self._inventory.list_files_for_article(article)
        num_files, file_size, extensions, _has_large, _unresolved, _all_unresolved = (
            self._inventory.summarize_inventory(files)
        )
        row["num_files"] = str(num_files)
        row["file_size"] = file_size
        row["extensions"] = extensions
        return row

    def fetch_article(self, article_id: int) -> dict[str, Any]:
        """
        Fetch full Figshare metadata for one ADC article.

        Args:
            article_id: Figshare article ID.

        Returns:
            Article JSON document.
        """
        return self._api.fetch_article(article_id)

    def list_article_ids(self, *, limit: int | None = None) -> list[int]:
        """
        Return merged ADC article IDs without fetching full metadata.

        Args:
            limit: Optional cap on returned IDs.

        Returns:
            Sorted unique Figshare article IDs.
        """
        return self._api.merge_article_ids(limit=limit)
