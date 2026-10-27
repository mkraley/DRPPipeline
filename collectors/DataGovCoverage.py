"""
Geographic and temporal coverage helpers for Data.gov catalog pages.

Geographic values are normalized to the ICPSR Geographic Names Thesaurus.
Coordinate / bounding-box strings are never stored as coverage text; they are
only used to infer vocabulary terms when possible.
"""

from __future__ import annotations

import re
from typing import Any

from collectors.AdcMetadataExtractor import bounding_box_from_geojson
from collectors.SsaCatalogJsonLd import temporal_fields
from collectors.SsaCompleteMetadata import (
    geographic_from_metadata_value,
    temporal_from_metadata_value,
)
from collectors.UsfsMetadataExtractor import normalize_temporal_date
from utils.IcpsrGeographicNormalizer import (
    GeographicNormalizeResult,
    normalize_geographic_metadata,
)
from utils.temporal_utils import pair_time_fields

_FOUR_FLOATS_RE = re.compile(
    r"^\s*"
    r"([+-]?\d+(?:\.\d+)?)\s*,\s*"
    r"([+-]?\d+(?:\.\d+)?)\s*,\s*"
    r"([+-]?\d+(?:\.\d+)?)\s*,\s*"
    r"([+-]?\d+(?:\.\d+)?)\s*$"
)
_COORD_HINT_RE = re.compile(
    r"^\s*[+-]?\d+(?:\.\d+)?(?:\s*,\s*[+-]?\d+(?:\.\d+)?){1,3}\s*$"
)


def catalog_date(value: Any) -> str:
    """
    Normalize a catalog date (issued/modified/coverage bound) to a storage value.

    Args:
        value: Raw catalog date string or other scalar.

    Returns:
        Year or ``YYYY-MM-DD`` when recognized; otherwise empty.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if "T" in text:
        text = text.split("T", 1)[0].strip()
    if "/" in text and text.count("-") >= 2:
        # Interval remnant; keep the first date-like token.
        text = text.split("/", 1)[0].strip()
    return normalize_temporal_date(text)


def looks_like_coordinates(text: str) -> bool:
    """
    Return True when ``text`` looks like lon/lat coordinates, not a place name.

    Args:
        text: Candidate spatial string.

    Returns:
        True for comma-separated numeric coordinate / bbox strings.
    """
    return bool(text and _COORD_HINT_RE.match(text.strip()))


def bounding_box_from_csv(text: str) -> dict[str, float] | None:
    """
    Parse a four-number CSV spatial string into west/east/south/north.

    Data.gov often stores ``lon,lat,lon,lat`` without guaranteeing min/max order.
    Longitude and latitude pairs are separated by treating values with
    ``abs(value) <= 90`` as latitude candidates when ambiguous; otherwise the
    common ``x,y,x,y`` layout is assumed and min/max are taken per axis.

    Args:
        text: Four comma-separated floats.

    Returns:
        Bounding box dict for ``normalize_geographic_metadata``, or None.
    """
    match = _FOUR_FLOATS_RE.match(text or "")
    if match is None:
        return None
    values = [float(match.group(index)) for index in range(1, 5)]
    xs = (values[0], values[2])
    ys = (values[1], values[3])
    # Prefer treating odd positions as latitude when both look like latitudes.
    if all(abs(value) <= 90.0 for value in ys) and any(abs(value) > 90.0 for value in xs):
        lons, lats = xs, ys
    elif all(abs(value) <= 90.0 for value in xs) and any(abs(value) > 90.0 for value in ys):
        lons, lats = ys, xs
    else:
        lons, lats = xs, ys
    return {
        "west": min(lons),
        "east": max(lons),
        "south": min(lats),
        "north": max(lats),
    }


def bounding_box_from_spatial(raw: Any) -> dict[str, float] | None:
    """
    Extract a bounding box from a Complete Metadata / JSON-LD spatial value.

    Args:
        raw: Spatial cell (string, Location JSON, or GeoJSON text).

    Returns:
        Bounding box dict, or None when coordinates are absent.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, list) and raw:
        boxes = [bounding_box_from_spatial(item) for item in raw]
        boxes = [box for box in boxes if box]
        if not boxes:
            return None
        return {
            "west": min(box["west"] for box in boxes),
            "east": max(box["east"] for box in boxes),
            "south": min(box["south"] for box in boxes),
            "north": max(box["north"] for box in boxes),
        }
    if isinstance(raw, dict):
        geo = raw.get("geo") if isinstance(raw.get("geo"), dict) else {}
        box_text = str(geo.get("box") or raw.get("box") or "").strip()
        if box_text:
            parts = [part for part in re.split(r"[\s,]+", box_text) if part]
            if len(parts) == 4:
                try:
                    south, west, north, east = (float(part) for part in parts)
                    return {
                        "west": min(west, east),
                        "east": max(west, east),
                        "south": min(south, north),
                        "north": max(south, north),
                    }
                except ValueError:
                    pass
        lat = geo.get("latitude")
        lon = geo.get("longitude")
        if lat is not None and lon is not None:
            try:
                latitude = float(lat)
                longitude = float(lon)
            except (TypeError, ValueError):
                return None
            return {
                "west": longitude,
                "east": longitude,
                "south": latitude,
                "north": latitude,
            }
        return None
    text = str(raw).strip()
    if not text:
        return None
    csv_box = bounding_box_from_csv(text)
    if csv_box is not None:
        return csv_box
    if text.startswith("{") or text.startswith("["):
        return bounding_box_from_geojson(text)
    return None


def normalize_catalog_geographic(raw_spatial: Any) -> GeographicNormalizeResult:
    """
    Map catalog spatial metadata to ICPSR geographic coverage terms.

    Coordinate-only values contribute a bounding box (never stored as text).
    Place labels are passed as place keywords / extent description.

    Args:
        raw_spatial: Complete Metadata ``spatial`` cell or JSON-LD spatial value.

    Returns:
        Normalization result (possibly empty when no vocabulary match exists).
    """
    bbox = bounding_box_from_spatial(raw_spatial)
    label = geographic_from_metadata_value(raw_spatial).strip()
    if looks_like_coordinates(label):
        label = ""
    keywords = [
        part.strip()
        for part in re.split(r"[;,]", label)
        if part.strip() and not looks_like_coordinates(part)
    ]
    return normalize_geographic_metadata(
        geographic_extent_description=label,
        place_keywords=keywords or None,
        bounding_box=bbox,
    )


def catalog_temporal_fields(
    *,
    title: str,
    dataset: dict[str, Any],
    complete_rows: dict[str, Any] | None = None,
) -> dict[str, str]:
    """
    Resolve time_start/time_end from catalog temporal metadata.

    Preference order:
    1. Complete Metadata ``temporal`` / JSON-LD ``temporalCoverage``
    2. Title date inference
    3. ``issued`` / ``datePublished`` as start and ``modified`` / ``dateModified``
       as end (each paired when only one is present)

    Args:
        title: Dataset title.
        dataset: JSON-LD Dataset object.
        complete_rows: Optional Complete Metadata name-to-value map.

    Returns:
        Paired ``time_start`` / ``time_end`` when any source yields dates.
    """
    rows = complete_rows or {}
    from_complete = temporal_from_metadata_value(rows.get("temporal"))
    if from_complete:
        return _normalize_time_dict(from_complete)

    from_json_ld = temporal_fields(title, dataset)
    if from_json_ld:
        return _normalize_time_dict(from_json_ld)

    issued = catalog_date(
        rows.get("issued")
        or dataset.get("datePublished")
        or dataset.get("issued")
    )
    modified = catalog_date(
        rows.get("modified")
        or dataset.get("dateModified")
        or dataset.get("modified")
    )
    if issued or modified:
        return pair_time_fields(issued or modified, modified or issued)
    return {}


def _normalize_time_dict(fields: dict[str, str]) -> dict[str, str]:
    """Truncate ISO timestamps in a paired time dict."""
    start = catalog_date(fields.get("time_start"))
    end = catalog_date(fields.get("time_end"))
    return pair_time_fields(start, end)
