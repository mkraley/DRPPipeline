"""
Enumerate FERC dataset candidates from the data-assets catalog.

Each nested dataset becomes one sourcing row (one DRPID per landing page).
Data-asset pages themselves are not sourced.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from sourcing.FercCatalogClient import FercCatalogClient
from utils.Logger import Logger

AGENCY = "Federal Energy Regulatory Commission"
_DATASET_HOST = "data.ferc.gov"


def canonical_dataset_url(url: str) -> str | None:
    """
    Return the canonical landing-page URL for a FERC dataset.

    Args:
        url: Catalog or stored source URL.

    Returns:
        ``https://data.ferc.gov/{asset}/{dataset}`` without a trailing slash,
        or None when the URL is not a dataset page.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.lower() != _DATASET_HOST:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    return f"https://{_DATASET_HOST}/{'/'.join(parts)}"


def rows_from_assets(assets: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    Flatten catalog assets into dataset candidate rows, ordered by dataset id.

    Args:
        assets: Objects from the data-assets API.

    Returns:
        Candidate rows with url, title, summary, agency, office, and record_id.
    """
    rows: list[dict[str, str]] = []
    for asset in assets:
        office = str(asset.get("program_office") or "").strip()
        datasets = asset.get("data-sets") or []
        if not isinstance(datasets, list):
            continue
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            row = dataset_candidate_row(dataset, office)
            if row is not None:
                rows.append(row)
    rows.sort(key=lambda row: int(row["record_id"]))
    return rows


def dataset_candidate_row(dataset: dict[str, Any], office: str) -> dict[str, str] | None:
    """
    Convert one nested dataset into a sourcing candidate.

    Args:
        dataset: One object from an asset's ``data-sets`` list.
        office: Parent asset program office.

    Returns:
        Candidate dict, or None when id, title, or landing URL is missing.
    """
    raw_id = dataset.get("id")
    if raw_id is None or str(raw_id).strip() == "":
        return None
    title = str(dataset.get("title") or "").strip()
    url = canonical_dataset_url(str(dataset.get("url") or ""))
    if not title or url is None:
        return None
    return {
        "url": url,
        "title": title,
        "summary": str(dataset.get("description") or "").strip(),
        "agency": AGENCY,
        "office": office,
        "record_id": str(raw_id).strip(),
    }


class FercCandidateFetcher:
    """List FERC catalog datasets and build storage-ready rows."""

    def __init__(self, *, client: FercCatalogClient | None = None) -> None:
        """
        Initialize the fetcher.

        Args:
            client: Catalog client (created when omitted).
        """
        self._client = client or FercCatalogClient()

    def list_dataset_rows(self) -> list[dict[str, str]]:
        """
        Return one candidate row per catalog dataset.

        Returns:
            Rows ordered by dataset id.
        """
        assets = self._client.fetch_data_assets()
        rows = rows_from_assets(assets)
        Logger.info("FERC catalog: %s data asset(s), %s dataset(s)", len(assets), len(rows))
        return rows

    def close(self) -> None:
        """Release the underlying catalog client."""
        self._client.close()
