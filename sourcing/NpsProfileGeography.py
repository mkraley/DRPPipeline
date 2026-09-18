"""
Map IRMA Units and Geography polygons onto DataLumos coverage.
"""

from __future__ import annotations

import re
from typing import Any

from utils.IcpsrGeographicNormalizer import normalize_geographic_metadata

_WKT_POINT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")


def profile_unit_names(profile: dict[str, Any]) -> list[str]:
    """Return NPS unit names from the Units list."""
    names: list[str] = []
    raw = profile.get("units") or []
    if not isinstance(raw, list):
        return names
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("unitName") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def profile_units(profile: dict[str, Any]) -> list[dict[str, str]]:
    """Return unit code/name pairs from the Units list."""
    units: list[dict[str, str]] = []
    raw = profile.get("units") or []
    if not isinstance(raw, list):
        return units
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("unitCode") or "").strip()
        name = str(item.get("unitName") or "").strip()
        if code or name:
            units.append({"code": code, "name": name})
    return units


def bbox_from_wkt(wkt: str) -> dict[str, float] | None:
    """Parse west/east/south/north from an IRMA POLYGON WKT string."""
    pairs = _WKT_POINT_RE.findall(wkt or "")
    if len(pairs) < 2:
        return None
    lons = [float(lon) for lon, _lat in pairs]
    lats = [float(lat) for _lon, lat in pairs]
    return {
        "west": min(lons),
        "east": max(lons),
        "south": min(lats),
        "north": max(lats),
    }


def profile_bounding_box(profile: dict[str, Any]) -> dict[str, float] | None:
    """Return the union bounding box of all Geography polygons."""
    boxes: list[dict[str, float]] = []
    raw = profile.get("boundingBoxes") or []
    if not isinstance(raw, list):
        return None
    for item in raw:
        if not isinstance(item, dict):
            continue
        box = bbox_from_wkt(str(item.get("wkt") or item.get("WKT") or ""))
        if box:
            boxes.append(box)
    if not boxes:
        return None
    return {
        "west": min(box["west"] for box in boxes),
        "east": max(box["east"] for box in boxes),
        "south": min(box["south"] for box in boxes),
        "north": max(box["north"] for box in boxes),
    }


def profile_geographic_coverage(profile: dict[str, Any]) -> str:
    """Map Units and Geography polygons to ICPSR geographic coverage."""
    names = profile_unit_names(profile)
    geo = normalize_geographic_metadata(
        geographic_extent_description="; ".join(names),
        place_keywords=names,
        bounding_box=profile_bounding_box(profile),
    )
    return geo.geographic_coverage
