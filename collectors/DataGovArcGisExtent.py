"""
Infer WGS84 bounding boxes from ArcGIS MapServer / FeatureServer metadata.
"""

from __future__ import annotations

import math
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from utils.Logger import Logger
from utils.url_utils import requests_verify

_ARCGIS_SERVICE_RE = re.compile(
    r"/arcgis/rest/services/.+/(?:MapServer|FeatureServer)(?:/\d+)?/?$",
    re.IGNORECASE,
)
_GEOGRAPHIC_WKIDS = frozenset({4326, 4269, 4267, 4152, 104000})
_WEB_MERCATOR_WKIDS = frozenset({3857, 102100, 102113, 900913})
_EARTH_RADIUS_M = 6378137.0
_DEFAULT_TIMEOUT_SEC = 60


def is_arcgis_map_or_feature_server(url: str) -> bool:
    """
    Return True when ``url`` looks like an ArcGIS MapServer or FeatureServer.

    Args:
        url: Resource URL.

    Returns:
        True for ArcGIS REST map/feature service endpoints.
    """
    path = urlsplit(url.strip()).path.rstrip("/")
    return bool(_ARCGIS_SERVICE_RE.search(path))


def is_arcgis_hub_or_item_page(url: str) -> bool:
    """
    Return True for ArcGIS Hub / Geoplatform item pages that print poorly to PDF.

    Args:
        url: Resource URL.

    Returns:
        True for interactive hub/item overview pages.
    """
    parsed = urlsplit(url.strip())
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "hub.arcgis.com" in host and "/datasets/" in path:
        return True
    if host.endswith("maps.arcgis.com") and "/home/item.html" in path:
        return True
    return False


def arcgis_json_url(service_url: str) -> str:
    """
    Build the ``?f=json`` metadata URL for an ArcGIS REST service.

    Args:
        service_url: MapServer or FeatureServer URL.

    Returns:
        Service URL with ``f=json`` query parameter.
    """
    parts = urlsplit(service_url.strip())
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["f"] = "json"
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/"), urlencode(query), "")
    )


def web_mercator_to_lon_lat(x: float, y: float) -> tuple[float, float]:
    """
    Convert a Web Mercator meter coordinate to WGS84 lon/lat.

    Args:
        x: Easting in meters.
        y: Northing in meters.

    Returns:
        ``(longitude, latitude)`` in decimal degrees.
    """
    lon = (x / _EARTH_RADIUS_M) * (180.0 / math.pi)
    lat = (2.0 * math.atan(math.exp(y / _EARTH_RADIUS_M)) - math.pi / 2.0) * (
        180.0 / math.pi
    )
    return lon, lat


def bounding_box_from_arcgis_extent(extent: dict[str, Any]) -> dict[str, float] | None:
    """
    Convert an ArcGIS ``fullExtent`` / ``extent`` object to WGS84 west/east/south/north.

    Args:
        extent: ArcGIS extent dict with xmin/ymin/xmax/ymax and spatialReference.

    Returns:
        Bounding box for ``normalize_geographic_metadata``, or None when invalid.
    """
    try:
        xmin = float(extent["xmin"])
        ymin = float(extent["ymin"])
        xmax = float(extent["xmax"])
        ymax = float(extent["ymax"])
    except (KeyError, TypeError, ValueError):
        return None
    spatial_ref = extent.get("spatialReference")
    wkid = _wkid_from_spatial_reference(spatial_ref)
    if wkid in _WEB_MERCATOR_WKIDS or (
        wkid is None and abs(xmin) > 180.0 and abs(xmax) > 180.0
    ):
        west_lon, south_lat = web_mercator_to_lon_lat(xmin, ymin)
        east_lon, north_lat = web_mercator_to_lon_lat(xmax, ymax)
        return {
            "west": min(west_lon, east_lon),
            "east": max(west_lon, east_lon),
            "south": min(south_lat, north_lat),
            "north": max(south_lat, north_lat),
        }
    if wkid is not None and wkid not in _GEOGRAPHIC_WKIDS and abs(xmin) > 180.0:
        Logger.debug("Skipping ArcGIS extent with unsupported WKID %s", wkid)
        return None
    return {
        "west": min(xmin, xmax),
        "east": max(xmin, xmax),
        "south": min(ymin, ymax),
        "north": max(ymin, ymax),
    }


def fetch_arcgis_service_extent(
    service_url: str,
    *,
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC,
) -> dict[str, float] | None:
    """
    Fetch MapServer/FeatureServer JSON and return a WGS84 bounding box.

    Args:
        service_url: ArcGIS REST service URL.
        timeout_sec: HTTP timeout.

    Returns:
        Bounding box dict, or None when the service has no usable extent.
    """
    if not is_arcgis_map_or_feature_server(service_url):
        return None
    json_url = arcgis_json_url(service_url)
    try:
        response = requests.get(
            json_url,
            timeout=timeout_sec,
            verify=requests_verify(),
            headers={"Accept": "application/json"},
        )
    except requests.RequestException as exc:
        Logger.warning("ArcGIS extent request failed for %s: %s", json_url, exc)
        return None
    if response.status_code >= 400:
        Logger.warning(
            "ArcGIS extent HTTP %s for %s",
            response.status_code,
            json_url,
        )
        return None
    try:
        payload = response.json()
    except ValueError:
        Logger.warning("ArcGIS extent response was not JSON: %s", json_url)
        return None
    if not isinstance(payload, dict):
        return None
    extent = payload.get("fullExtent") or payload.get("extent") or payload.get(
        "initialExtent"
    )
    if not isinstance(extent, dict):
        return None
    return bounding_box_from_arcgis_extent(extent)


def first_arcgis_extent_from_urls(urls: list[str]) -> dict[str, float] | None:
    """
    Return the first usable WGS84 bbox from a list of resource URLs.

    Args:
        urls: Catalog download and HTML resource URLs.

    Returns:
        Bounding box dict, or None when none of the URLs yield an extent.
    """
    for url in urls:
        box = fetch_arcgis_service_extent(url)
        if box is not None:
            return box
    return None


def _wkid_from_spatial_reference(spatial_ref: Any) -> int | None:
    """Return the best available WKID from an ArcGIS spatialReference object."""
    if not isinstance(spatial_ref, dict):
        return None
    for key in ("latestWkid", "wkid"):
        value = spatial_ref.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None
