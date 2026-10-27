"""
Enumerate SSA dataset candidates from the Data.gov catalog.

Thin wrapper around ``DataGovCandidateFetcher`` with SSA agency labels.
Re-exports shared helpers used by the SSA collector.
"""

from __future__ import annotations

from sourcing.DataGovCandidateFetcher import (
    CATALOG_DATASET_PREFIX,
    FILE_FORMATS,
    FILE_SUFFIXES,
    HTML_FORMATS,
    DataGovCandidateFetcher,
    catalog_url_from_slug,
    has_collectible_file,
    is_file_download,
    is_html_url,
    is_public_dataset,
    slug_from_source_url,
)
from sourcing.SsaCatalogClient import SsaCatalogClient

AGENCY = "Social Security Administration"
OFFICE = "Social Security Administration"

__all__ = [
    "AGENCY",
    "CATALOG_DATASET_PREFIX",
    "FILE_FORMATS",
    "FILE_SUFFIXES",
    "HTML_FORMATS",
    "OFFICE",
    "SsaCandidateFetcher",
    "catalog_url_from_slug",
    "has_collectible_file",
    "is_file_download",
    "is_html_url",
    "is_public_dataset",
    "slug_from_source_url",
]


class SsaCandidateFetcher(DataGovCandidateFetcher):
    """List SSA catalog datasets and build storage-ready rows."""

    def __init__(
        self,
        *,
        client: SsaCatalogClient | None = None,
        request_delay: float | None = None,
    ) -> None:
        """
        Initialize the SSA fetcher.

        Args:
            client: Catalog client (created when omitted).
            request_delay: Seconds between search pages; defaults to
                ``datagov_request_delay`` / ``ssa_request_delay`` or 0.1.
        """
        super().__init__(
            agency=AGENCY,
            office=OFFICE,
            client=client or SsaCatalogClient(),
            request_delay=request_delay,
            source_label="SSA",
        )
