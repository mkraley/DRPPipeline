"""
Fetch one EDG Clip and Ship item and map it to collection metadata.
"""

from __future__ import annotations

from typing import Any

import requests

from sourcing.EpaHubCandidateFetcher import row_from_feature
from sourcing.EpaHubCatalogClient import DEFAULT_ITEMS_URL
from sourcing.EpaSourcing import AGENCY
from utils.datalumos_data_types import DATA_TYPE_GIS
from utils.url_utils import requests_verify

_GEOSPATIAL_TYPES = {"feature service", "map service", "service definition"}


class EpaHubItemClient:
    """Load one Hub search feature by ArcGIS item id."""

    def __init__(
        self,
        *,
        getter: Any | None = None,
        items_url: str | None = None,
        timeout_sec: int = 60,
    ) -> None:
        """
        Initialize the item client.

        Args:
            getter: ``requests.get`` replacement for tests.
            items_url: Items collection URL. Defaults to the Clip and Ship catalog.
            timeout_sec: HTTP timeout.
        """
        self._get = getter or requests.get
        self._items_url = (items_url or DEFAULT_ITEMS_URL).rstrip("/")
        self._timeout_sec = timeout_sec

    def fetch_feature(self, item_id: str) -> dict[str, Any]:
        """
        Return the GeoJSON feature for ``item_id``.

        Args:
            item_id: ArcGIS item id.

        Returns:
            Feature object from the Hub search API.

        Raises:
            RuntimeError: When the item request fails.
        """
        response = self._get(
            f"{self._items_url}/{item_id.strip()}",
            timeout=self._timeout_sec,
            headers={"Accept": "application/geo+json"},
            verify=requests_verify(),
        )
        if getattr(response, "status_code", 200) >= 400:
            raise RuntimeError(
                f"EDG item HTTP {response.status_code} for {item_id}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("EDG item response was not JSON") from exc
        if not isinstance(payload, dict) or not str(payload.get("id") or "").strip():
            raise RuntimeError(f"EDG item {item_id} was not a feature")
        return payload


def metadata_from_feature(feature: dict[str, Any]) -> dict[str, Any]:
    """
    Map a Hub feature to Storage metadata fields.

    Args:
        feature: GeoJSON feature from the Clip and Ship catalog.

    Returns:
        Title, summary, agency, office, keywords, and data type.
    """
    row = row_from_feature(feature) or {}
    properties = feature.get("properties")
    props = properties if isinstance(properties, dict) else {}
    item_type = str(props.get("type") or "")
    fields: dict[str, Any] = {
        "title": row.get("title") or str(props.get("title") or "").strip(),
        "summary": row.get("summary") or "",
        "agency": AGENCY,
        "office": row.get("office") or AGENCY,
        "keywords": _keywords(props.get("tags")),
    }
    if item_type.strip().casefold() in _GEOSPATIAL_TYPES:
        fields["data_types"] = DATA_TYPE_GIS
    return fields


def service_url_from_feature(feature: dict[str, Any]) -> str:
    """
    Return the MapServer or FeatureServer URL on a Hub feature.

    Args:
        feature: GeoJSON feature.

    Returns:
        Service URL, or an empty string when the item has none.
    """
    from collectors.DataGovArcGisExtent import is_arcgis_map_or_feature_server

    properties = feature.get("properties")
    props = properties if isinstance(properties, dict) else {}
    url = str(props.get("url") or "").strip()
    if is_arcgis_map_or_feature_server(url):
        return url
    return ""


def bbox_from_geometry(geometry: Any) -> dict[str, float] | None:
    """
    Return a WGS84 bounding box for a GeoJSON geometry.

    Args:
        geometry: GeoJSON geometry object.

    Returns:
        ``west`` / ``south`` / ``east`` / ``north``, or None when empty.
    """
    points: list[tuple[float, float]] = []
    _collect_points(geometry.get("coordinates") if isinstance(geometry, dict) else None, points)
    if not points:
        return None
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return {
        "west": min(lons),
        "south": min(lats),
        "east": max(lons),
        "north": max(lats),
    }


def _keywords(tags: Any) -> str:
    """Join Hub tags into a comma-separated keyword string."""
    if isinstance(tags, str):
        return tags.strip()
    if not isinstance(tags, list):
        return ""
    values = [str(tag).strip() for tag in tags if str(tag).strip()]
    return ", ".join(values)


def _collect_points(value: Any, points: list[tuple[float, float]]) -> None:
    """Append coordinate pairs from a nested GeoJSON coordinates array."""
    if not isinstance(value, (list, tuple)):
        return
    if (
        len(value) >= 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        points.append((float(value[0]), float(value[1])))
        return
    for item in value:
        _collect_points(item, points)
