"""
Map IRMA Units and Geography polygons onto DataLumos coverage.
"""

from __future__ import annotations

import re
from typing import Any

from utils.IcpsrGeographicNormalizer import normalize_geographic_metadata

_WKT_POINT_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")

# Park units only. Inventory & Monitoring networks (APHN, etc.) are not places.
_NPS_UNIT_STATES: dict[str, tuple[str, ...]] = {
    "BLRI": ("North Carolina", "Virginia"),
    "BISO": ("Kentucky", "Tennessee"),
    "OBRI": ("Tennessee",),
}

# NPS System designation suffixes (longest first). Based on NPS park-unit
# abbreviations: https://www.nps.gov/subjects/legal/nps-park-units-by-congressional-district-119th-congress.htm
_NPS_DESIGNATION_SUFFIXES: tuple[str, ...] = (
    "National Historical Park and Preserve",
    "National Historical Park & Preserve",
    "National Monument and Preserve",
    "National Monument & Preserve",
    "National Park and Preserve",
    "National Park & Preserve",
    "National River and Recreation Area",
    "National River & Recreation Area",
    "National River and Recreational Area",
    "National Scenic and Recreational River",
    "National Scenic & Recreational River",
    "Scenic and Recreational River",
    "Scenic & Recreational River",
    "Wild and Scenic River",
    "Wild & Scenic River",
    "Inventory and Monitoring Network",
    "Inventory & Monitoring Network",
    "International Historic Site",
    "National Battlefield Park",
    "National Battlefield Site",
    "National Historical Park",
    "National Historic Trail",
    "National Scenic Riverway",
    "National Scenic River",
    "National Recreational River",
    "National Recreation Area",
    "National Military Park",
    "National Historic Site",
    "National Battlefield",
    "National Lakeshore",
    "National Seashore",
    "National Preserve",
    "National Reserve",
    "National Memorial",
    "National Monument",
    "National River",
    "National Park",
    "Wild River",
    "Parkway",
    "Network",
)

_DESIGNATION_SUFFIX_RE = re.compile(
    r"(?:^|\s+)(?:"
    + "|".join(re.escape(suffix) for suffix in _NPS_DESIGNATION_SUFFIXES)
    + r")\s*$",
    re.IGNORECASE,
)


def short_unit_name(name: str) -> str:
    """
    Strip an NPS designation suffix from a unit name.

    Examples:
        ``Blue Ridge Parkway`` -> ``Blue Ridge``
        ``Obed Wild and Scenic River`` -> ``Obed``
        ``Appalachian Highlands Network`` -> ``Appalachian Highlands``
    """
    text = " ".join((name or "").split()).strip()
    if not text:
        return ""
    while True:
        updated = _DESIGNATION_SUFFIX_RE.sub("", text).strip(" ,;-")
        if updated == text:
            return text
        text = updated


def profile_short_unit_names(profile: dict[str, Any]) -> list[str]:
    """Return designation-stripped unit names suitable for keyword lists."""
    short_names: list[str] = []
    for name in profile_unit_names(profile):
        short = short_unit_name(name)
        if short and short not in short_names:
            short_names.append(short)
    return short_names


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


def profile_states_from_units(profile: dict[str, Any]) -> list[str]:
    """
    Map park unit codes to ICPSR state terms.

    Network-level units (for example APHN) are skipped; only known park codes
    contribute states.
    """
    states: list[str] = []
    for unit in profile_units(profile):
        code = unit.get("code", "").upper()
        for state in _NPS_UNIT_STATES.get(code, ()):
            if state not in states:
                states.append(state)
    return states


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
    states = profile_states_from_units(profile)
    geo = normalize_geographic_metadata(
        geographic_extent_description="; ".join(names),
        place_keywords=states + names,
        bounding_box=profile_bounding_box(profile),
    )
    return geo.geographic_coverage
