"""
Enumerate SSA dataset candidates from the Data.gov catalog.

Keeps public datasets that list at least one non-HTML file download. Each
catalog slug becomes one sourcing row (one DRPID per time period).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sourcing.SsaCatalogClient import SsaCatalogClient
from utils.Args import Args
from utils.Logger import Logger

AGENCY = "Social Security Administration"
OFFICE = "Social Security Administration"
CATALOG_DATASET_PREFIX = "https://catalog.data.gov/dataset/"
FILE_FORMATS = frozenset({"CSV", "XLSX", "XLS", "ZIP", "JSON", "PDF", "XML", "TXT"})
FILE_SUFFIXES = frozenset({".csv", ".xlsx", ".xls", ".zip", ".json", ".pdf", ".xml", ".txt"})
HTML_FORMATS = frozenset({"HTML", "HTM"})


def catalog_url_from_slug(slug: str) -> str:
    """
    Build the catalog.data.gov dataset URL for a slug.

    Args:
        slug: Catalog dataset slug.

    Returns:
        Canonical catalog dataset URL.
    """
    return f"{CATALOG_DATASET_PREFIX}{slug.strip().strip('/')}"


def slug_from_source_url(source_url: str) -> str | None:
    """
    Extract the catalog dataset slug from a source URL.

    Args:
        source_url: Catalog dataset URL.

    Returns:
        Slug string, or None when the URL is not a catalog dataset page.
    """
    parsed = urlparse(source_url.strip())
    if parsed.netloc != "catalog.data.gov":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] != "dataset":
        return None
    slug = parts[1].strip()
    return slug or None


def is_file_download(distribution: dict[str, Any]) -> bool:
    """
    Return True when a DCAT distribution is a non-HTML downloadable file.

    Args:
        distribution: DCAT distribution object.

    Returns:
        True when ``downloadURL`` points at a known file format.
    """
    url = str(distribution.get("downloadURL") or "").strip()
    if not url:
        return False
    fmt = str(distribution.get("format") or "").upper()
    if fmt in HTML_FORMATS:
        return False
    if fmt in FILE_FORMATS:
        return True
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix in FILE_SUFFIXES


def is_public_dataset(result: dict[str, Any]) -> bool:
    """
    Return True when catalog accessLevel is public.

    Args:
        result: One GSA search result.

    Returns:
        True for public datasets.
    """
    dcat = result.get("dcat") if isinstance(result.get("dcat"), dict) else {}
    access = str(dcat.get("accessLevel") or result.get("accessLevel") or "")
    return access.strip().lower() == "public"


def has_collectible_file(result: dict[str, Any]) -> bool:
    """
    Return True when the dataset lists at least one non-HTML file.

    Args:
        result: One GSA search result.

    Returns:
        True when a file download is present.
    """
    dcat = result.get("dcat") if isinstance(result.get("dcat"), dict) else {}
    distributions = dcat.get("distribution") or []
    if not isinstance(distributions, list):
        return False
    return any(
        isinstance(item, dict) and is_file_download(item) for item in distributions
    )


class SsaCandidateFetcher:
    """List SSA catalog datasets and build storage-ready rows."""

    def __init__(
        self,
        *,
        client: SsaCatalogClient | None = None,
        request_delay: float | None = None,
    ) -> None:
        """
        Initialize the fetcher.

        Args:
            client: Catalog client (created when omitted).
            request_delay: Seconds between search pages; defaults to
                ``ssa_request_delay`` from Args or 0.1.
        """
        self._client = client or SsaCatalogClient()
        default_delay = float(getattr(Args, "ssa_request_delay", 0.1) or 0.1)
        self._request_delay = request_delay if request_delay is not None else default_delay

    def list_dataset_rows(self) -> list[dict[str, str]]:
        """
        Return public SSA catalog rows that have a downloadable file.

        Returns:
            Candidate rows with url, title, agency, office, and record_id (slug).
        """
        rows: list[dict[str, str]] = []
        after: str | None = None
        pages = 0
        while True:
            payload = self._client.fetch_search_page(after=after)
            results = payload.get("results") or []
            pages += 1
            if not isinstance(results, list):
                break
            for result in results:
                if not isinstance(result, dict):
                    continue
                row = self.build_candidate_row(result)
                if row is not None:
                    rows.append(row)
            Logger.debug(
                "SSA catalog page %s: %s hits, %s collectible so far",
                pages,
                len(results),
                len(rows),
            )
            after = payload.get("after")
            if not after or not results:
                break
            if self._request_delay > 0:
                time.sleep(self._request_delay)
        return rows

    def build_candidate_row(self, result: dict[str, Any]) -> dict[str, str] | None:
        """
        Convert a GSA search hit to a sourcing candidate row.

        Args:
            result: One catalog search result.

        Returns:
            Candidate dict, or None when the hit is not collectible.
        """
        slug = str(result.get("slug") or "").strip()
        title = str(result.get("title") or "").strip()
        if not slug or not title:
            return None
        if not is_public_dataset(result) or not has_collectible_file(result):
            return None
        dcat = result.get("dcat") if isinstance(result.get("dcat"), dict) else {}
        identifier = str(dcat.get("identifier") or result.get("identifier") or "")
        return {
            "url": catalog_url_from_slug(slug),
            "title": title,
            "agency": AGENCY,
            "office": OFFICE,
            "record_id": slug,
            "identifier": identifier,
        }

    def close(self) -> None:
        """Release the underlying catalog client."""
        self._client.close()
