"""
Parse metadata and file downloads from catalog.data.gov SSA dataset pages.

Thin wrapper around ``DataGovMetadataExtractor`` with SSA agency labels.
"""

from __future__ import annotations

from typing import Any

from collectors.DataGovMetadataExtractor import (
    DataGovDownloadFile,
    filename_from_url,
    parse_download_files,
    parse_html_resources,
)
from collectors.DataGovMetadataExtractor import (
    parse_catalog_page as parse_datagov_catalog_page,
)
from sourcing.SsaCandidateFetcher import AGENCY, OFFICE

SsaDownloadFile = DataGovDownloadFile

__all__ = [
    "AGENCY",
    "OFFICE",
    "SsaDownloadFile",
    "filename_from_url",
    "parse_catalog_page",
    "parse_download_files",
    "parse_html_resources",
]


def parse_catalog_page(html: str, page_url: str) -> dict[str, Any]:
    """
    Parse an SSA catalog.data.gov dataset page into Storage-oriented fields.

    Args:
        html: Catalog dataset HTML.
        page_url: Canonical source URL.

    Returns:
        Metadata dict plus ``_download_files``, ``_html_resources``,
        and ``_format_label``.
    """
    return parse_datagov_catalog_page(
        html,
        page_url,
        agency=AGENCY,
        office=OFFICE,
    )
