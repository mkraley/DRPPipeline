"""
Enumerate Data.gov catalog dataset candidates for one organization.

Keeps public datasets that list at least one non-HTML file download. Each
catalog slug becomes one sourcing row (one DRPID per time period).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sourcing.DataGovCatalogClient import DataGovCatalogClient
from utils.Args import Args
from utils.Logger import Logger

CATALOG_DATASET_PREFIX = "https://catalog.data.gov/dataset/"
FILE_FORMATS = frozenset(
    {
        "CSV",
        "XLSX",
        "XLS",
        "ZIP",
        "JSON",
        "PDF",
        "XML",
        "TXT",
        "GEOJSON",
        "GDB",
        "SHP",
        "TIFF",
        "TIF",
        "PARQUET",
        "PARQ",
        "NC",
    }
)
FILE_SUFFIXES = frozenset(
    {
        ".csv",
        ".xlsx",
        ".xls",
        ".zip",
        ".json",
        ".pdf",
        ".xml",
        ".txt",
        ".geojson",
        ".gdb",
        ".shp",
        ".tiff",
        ".tif",
        ".parquet",
        ".parq",
        ".nc",
    }
)
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
    if is_html_url(url, fmt):
        return False
    if fmt in FILE_FORMATS:
        return True
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix in FILE_SUFFIXES


def is_html_url(url: str, fmt: str = "") -> bool:
    """
    Return True when a resource is an HTML landing page.

    Args:
        url: Resource URL.
        fmt: Catalog format token when present.

    Returns:
        True for HTML/HTM format labels or ``.html``/``.htm`` suffixes.
    """
    if not url.strip():
        return False
    if fmt.strip().upper() in HTML_FORMATS:
        return True
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix in {".html", ".htm"}


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


def _default_request_delay() -> float:
    """Return page delay from Args (generic key, then SSA legacy key)."""
    for attr in ("datagov_request_delay", "ssa_request_delay"):
        value = getattr(Args, attr, None)
        if value is not None:
            return float(value)
    return 0.1


class DataGovCandidateFetcher:
    """List Data.gov catalog datasets and build storage-ready rows."""

    def __init__(
        self,
        *,
        agency: str,
        office: str,
        client: DataGovCatalogClient | None = None,
        org_slug: str | None = None,
        request_delay: float | None = None,
        source_label: str | None = None,
    ) -> None:
        """
        Initialize the fetcher.

        Args:
            agency: Agency label written on sourced rows.
            office: Office label written on sourced rows.
            client: Catalog client (created when omitted).
            org_slug: Organization slug when ``client`` is omitted.
            request_delay: Seconds between search pages; defaults to
                ``datagov_request_delay`` / ``ssa_request_delay`` or 0.1.
            source_label: Short label for log lines (defaults to org slug).
        """
        if client is None:
            if not org_slug or not str(org_slug).strip():
                raise ValueError("org_slug is required when client is omitted")
            client = DataGovCatalogClient(org_slug=str(org_slug).strip())
        self._client = client
        self._agency = agency
        self._office = office
        self._request_delay = (
            request_delay if request_delay is not None else _default_request_delay()
        )
        self._source_label = (
            (source_label or self._client.org_slug).strip().upper() or "DATAGOV"
        )

    def list_dataset_rows(self) -> list[dict[str, str]]:
        """
        Return public catalog rows that have a downloadable file.

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
                "%s catalog page %s: %s hits, %s collectible so far",
                self._source_label,
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
            "agency": self._agency,
            "office": self._office,
            "record_id": slug,
            "identifier": identifier,
        }

    def close(self) -> None:
        """Release the underlying catalog client."""
        self._client.close()
