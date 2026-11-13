"""
Fetch one EDG Clip and Ship item and map it to collection metadata.
"""

from __future__ import annotations

from typing import Any

import requests

from collectors.EpaHubMetadata import metadata_from_feature
from sourcing.EpaHubCatalogClient import DEFAULT_ITEMS_URL
from utils.url_utils import requests_verify

__all__ = [
    "EpaHubItemClient",
    "bbox_from_geometry",
    "metadata_from_feature",
    "service_url_from_feature",
]


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

    def data_updated_ms(self, service_url: str) -> int | None:
        """
        Return the feature layer's data-updated time.

        Args:
            service_url: FeatureServer or MapServer URL.

        Returns:
            ``editingInfo.dataLastEditDate`` in epoch milliseconds, or None.
        """
        url = service_url.strip().rstrip("/")
        if not url:
            return None
        latest: int | None = None
        for layer_id in _layer_ids(self._read_json(url)):
            updated = _edit_date(self._read_json(f"{url}/{layer_id}"))
            if updated is not None and (latest is None or updated > latest):
                latest = updated
        return latest

    def _read_json(self, url: str) -> dict[str, Any] | None:
        """GET ArcGIS JSON. None means the request failed or returned an error."""
        try:
            response = self._get(
                url,
                params={"f": "json"},
                timeout=self._timeout_sec,
                verify=requests_verify(),
            )
            payload = response.json()
        except (TypeError, ValueError, OSError, requests.RequestException):
            return None
        if getattr(response, "status_code", 500) >= 400 or not isinstance(payload, dict):
            return None
        if isinstance(payload.get("error"), dict):
            return None
        return payload


def _layer_ids(payload: dict[str, Any] | None) -> list[int]:
    """Return feature layer ids, or layer 0 when the service lists none."""
    layers = payload.get("layers") if isinstance(payload, dict) else None
    if not isinstance(layers, list):
        return [0]
    ids = [number for layer in layers if (number := _layer_id(layer)) is not None]
    return ids or [0]


def _layer_id(layer: Any) -> int | None:
    """Return a layer id, including 0."""
    if not isinstance(layer, dict):
        return None
    try:
        number = int(layer.get("id"))
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _edit_date(payload: dict[str, Any] | None) -> int | None:
    """Return ``editingInfo.dataLastEditDate`` when present."""
    if not isinstance(payload, dict):
        return None
    info = payload.get("editingInfo")
    if not isinstance(info, dict):
        return None
    return _positive_int(info.get("dataLastEditDate"))


def _positive_int(value: Any) -> int | None:
    """Return a positive int, or None."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


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
