"""
Enumerate EDG Clip and Ship catalog items as sourcing rows.

Each Hub search item becomes one row (one DRPID per item id).
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from sourcing.EpaHubCatalogClient import EpaHubCatalogClient
from sourcing.EpaSourcing import AGENCY

HUB_ORIGIN = "https://edg-epa.hub.arcgis.com"
_ITEM_ID = re.compile(r"[0-9a-fA-F]{32}")
_HUB_HOST_SUFFIXES = (".hub.arcgis.com", ".maps.arcgis.com")


def hub_item_url(item_id: str, item_type: str) -> str:
    """
    Return the public Hub page for a catalog item.

    Args:
        item_id: ArcGIS item id.
        item_type: Hub type, such as ``Feature Service`` or ``Hub Page``.

    Returns:
        Dataset, document, or page URL on the Clip and Ship site.
    """
    return f"{HUB_ORIGIN}/{_section_for_type(item_type)}/{item_id.strip().lower()}"


def item_id_from_source_url(source_url: str) -> str | None:
    """
    Extract an ArcGIS item id from a Hub or item-page URL.

    Args:
        source_url: Stored or candidate source URL.

    Returns:
        Lowercase 32-character id, or None when the URL is not a Hub item.
    """
    parsed = urlparse(source_url.strip())
    if not _is_hub_host(parsed.netloc):
        return None
    query_id = parse_qs(parsed.query).get("id", [""])[0]
    if _ITEM_ID.fullmatch(query_id):
        return query_id.lower()
    for part in parsed.path.split("/"):
        if _ITEM_ID.fullmatch(part):
            return part.lower()
    return None


def rows_from_features(features: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    Convert Hub features into sourcing rows, ordered by title.

    Args:
        features: GeoJSON features from the items endpoint.

    Returns:
        Candidate rows. Duplicate item ids keep the first feature.
    """
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for feature in features:
        row = row_from_feature(feature)
        if row is None or row["record_id"] in seen:
            continue
        seen.add(row["record_id"])
        rows.append(row)
    rows.sort(key=lambda row: (row["title"].casefold(), row["record_id"]))
    return rows


def row_from_feature(feature: dict[str, Any]) -> dict[str, str] | None:
    """
    Convert one Hub feature into a sourcing candidate.

    Args:
        feature: One GeoJSON feature.

    Returns:
        Candidate dict, or None when the id or title is missing.
    """
    properties = feature.get("properties")
    props = properties if isinstance(properties, dict) else {}
    item_id = str(feature.get("id") or props.get("id") or "").strip().lower()
    title = str(props.get("title") or "").strip()
    if not _ITEM_ID.fullmatch(item_id) or not title:
        return None
    item_type = str(props.get("type") or "").strip()
    office = str(props.get("source") or "").strip() or AGENCY
    return {
        "url": hub_item_url(item_id, item_type),
        "title": title,
        "summary": " ".join(str(props.get("snippet") or "").split()),
        "agency": AGENCY,
        "office": office,
        "record_id": item_id,
        "item_type": item_type,
    }


class EpaHubCandidateFetcher:
    """List Clip and Ship items and build storage-ready rows."""

    def __init__(self, *, client: EpaHubCatalogClient | None = None) -> None:
        """
        Initialize the fetcher.

        Args:
            client: Catalog client (created when omitted).
        """
        self._client = client or EpaHubCatalogClient()

    def list_dataset_rows(self) -> list[dict[str, str]]:
        """
        Return one candidate row per catalog item.

        Returns:
            Rows ordered by title.
        """
        return rows_from_features(self._client.fetch_items())

    def close(self) -> None:
        """Close the catalog client."""
        self._client.close()


def _section_for_type(item_type: str) -> str:
    """Return the Hub path section for an item type."""
    kind = item_type.strip().casefold()
    if kind == "hub page":
        return "pages"
    if kind == "service definition":
        return "documents"
    return "datasets"


def _is_hub_host(netloc: str) -> bool:
    """Return True for ArcGIS Hub and ArcGIS Online item hosts."""
    host = netloc.lower()
    return host.endswith(_HUB_HOST_SUFFIXES)
