"""
Extract Storage metadata fields from Figshare article JSON for ARC datasets.
"""

from __future__ import annotations

import json
import re
from typing import Any

from collectors.UsfsMetadataExtractor import (
    DATA_TYPE_GIS,
    DATA_TYPE_PROGRAM_SOURCE,
    infer_data_types,
    normalize_temporal_date,
)
from utils.temporal_utils import apply_temporal_inference
from utils.IcpsrGeographicNormalizer import (
    GeographicNormalizeResult,
    log_geographic_normalization,
    normalize_geographic_metadata,
)
from utils.summary_html import normalize_summary_html_for_datalumos

_GIS_FILE_EXTENSIONS = frozenset({
    "tif", "tiff", "shp", "gdb", "geojson", "gpkg", "geotiff",
})
_GIS_ISO_TOPICS = frozenset({
    "imagerybasemapsearthcover",
    "elevation",
    "environment",
    "location",
    "planningcadastre",
})


def custom_field_value(article: dict[str, Any], field_name: str) -> str:
    """
    Return the first scalar value for a Figshare custom field by name.

    Args:
        article: Full Figshare article JSON.
        field_name: Custom field label (e.g. ``Geographic Coverage``).

    Returns:
        String value, or empty string when absent.
    """
    for field in article.get("custom_fields") or []:
        if str(field.get("name") or "") != field_name:
            continue
        value = field.get("value")
        if value is None:
            return ""
        if isinstance(value, list):
            return str(value[0]) if value else ""
        return str(value).strip()
    return ""


def extract_collection_notes(article: dict[str, Any]) -> str:
    """
    Build collection notes from the article DOI and optional citation.

    Args:
        article: Full Figshare article JSON.

    Returns:
        Newline-separated notes for Storage ``collection_notes``.
    """
    lines: list[str] = []
    doi = str(article.get("doi") or "").strip()
    if doi:
        lines.append(f"DOI: {doi}")
    citation = custom_field_value(article, "Preferred dataset citation")
    if citation and citation not in lines:
        lines.append(f"Citation: {citation}")
    return "\n".join(lines)


def extract_temporal_fields(article: dict[str, Any]) -> dict[str, str]:
    """
    Map ARC temporal custom fields to Storage ``time_start`` / ``time_end``.

    When the end date is missing, infers it from embedded dates in file names,
    then pairs partial ranges for DataLumos (both bounds or neither).

    Args:
        article: Full Figshare article JSON.

    Returns:
        Dict with optional ``time_start`` and ``time_end`` keys.
    """
    start = normalize_temporal_date(custom_field_value(article, "Temporal Extent Start Date"))
    end = normalize_temporal_date(custom_field_value(article, "Temporal Extent End Date"))
    filenames = [
        str(file_obj.get("name") or "")
        for file_obj in (article.get("files") or [])
        if file_obj.get("name")
    ]
    return apply_temporal_inference(start, end, filenames=filenames)


def _collect_coordinates(node: Any, coords: list[tuple[float, float]]) -> None:
    """Recursively collect lon/lat pairs from GeoJSON coordinate arrays."""
    if isinstance(node, list):
        if (
            len(node) >= 2
            and isinstance(node[0], (int, float))
            and isinstance(node[1], (int, float))
            and not isinstance(node[0], bool)
        ):
            coords.append((float(node[0]), float(node[1])))
            return
        for item in node:
            _collect_coordinates(item, coords)
    elif isinstance(node, dict):
        for value in node.values():
            _collect_coordinates(value, coords)


def bounding_box_from_geojson(text: str) -> dict[str, float] | None:
    """
    Compute a west/east/south/north bounding box from GeoJSON text.

    Args:
        text: GeoJSON string from the ``Geographic Coverage`` custom field.

    Returns:
        Bounding box dict for :func:`normalize_geographic_metadata`, or None.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    coords: list[tuple[float, float]] = []
    _collect_coordinates(payload, coords)
    if not coords:
        return None
    lons = [lon for lon, _lat in coords]
    lats = [lat for _lon, lat in coords]
    return {
        "west": min(lons),
        "east": max(lons),
        "south": min(lats),
        "north": max(lats),
    }


def normalize_geographic_coverage(article: dict[str, Any]) -> GeographicNormalizeResult:
    """
    Infer ICPSR geographic coverage from ARC custom fields.

    Args:
        article: Full Figshare article JSON.

    Returns:
        Normalization result with ``geographic_coverage`` and review warnings.
    """
    raw_geo = custom_field_value(article, "Geographic Coverage")
    extent = ""
    bbox: dict[str, float] | None = None
    if raw_geo.startswith("{"):
        bbox = bounding_box_from_geojson(raw_geo)
    elif raw_geo:
        extent = raw_geo
    return normalize_geographic_metadata(
        geographic_extent_description=extent,
        bounding_box=bbox,
    )


def infer_arc_data_types(article: dict[str, Any]) -> str:
    """
    Infer DataLumos data type(s) from title, description, and ARC-specific hints.

    Args:
        article: Full Figshare article JSON.

    Returns:
        Semicolon-delimited data type labels, or empty string.
    """
    title = str(article.get("title") or "")
    summary = str(article.get("description") or "")
    inferred = infer_data_types(title, summary, "")
    if inferred:
        return inferred

    defined_type = str(article.get("defined_type_name") or "").lower()
    if defined_type in {"software", "code"}:
        return DATA_TYPE_PROGRAM_SOURCE

    iso_topics = {
        str(topic).lower().replace(" ", "")
        for topic in _custom_field_list(article, "ISO Topic Category")
    }
    if iso_topics & _GIS_ISO_TOPICS:
        return DATA_TYPE_GIS

    extensions = {
        str(file_obj.get("name") or "").rsplit(".", 1)[-1].lower()
        for file_obj in (article.get("files") or [])
        if "." in str(file_obj.get("name") or "")
    }
    if extensions & _GIS_FILE_EXTENSIONS:
        return DATA_TYPE_GIS

    if custom_field_value(article, "Geographic Coverage").startswith("{"):
        if _text_suggests_gis(f"{title} {summary}"):
            return DATA_TYPE_GIS

    return ""


def extract_metadata(article: dict[str, Any]) -> dict[str, Any]:
    """
    Map a Figshare article document to Storage metadata fields.

    Args:
        article: Full Figshare article JSON from the public API.

    Returns:
        Dict with title, summary, keywords, temporal, geographic, data_types,
        collection_notes, and internal ``_geo_warnings`` for the collector.
    """
    tags = article.get("tags") or []
    keyword_parts: list[str] = []
    for tag in tags:
        if isinstance(tag, dict):
            keyword_parts.append(str(tag.get("name") or ""))
        else:
            keyword_parts.append(str(tag))
    keywords = ", ".join(part for part in keyword_parts if part)

    result: dict[str, Any] = {
        "title": str(article.get("title") or ""),
        "summary": normalize_summary_html_for_datalumos(
            str(article.get("description") or "")
        ),
        "keywords": keywords,
    }

    notes = extract_collection_notes(article)
    if notes:
        result["collection_notes"] = notes

    result.update(extract_temporal_fields(article))

    data_types = infer_arc_data_types(article)
    if data_types:
        result["data_types"] = data_types

    geo = normalize_geographic_coverage(article)
    log_geographic_normalization(
        geo,
        geographic_extent_description=custom_field_value(article, "Geographic Coverage"),
        bounding_box=bounding_box_from_geojson(custom_field_value(article, "Geographic Coverage"))
        if custom_field_value(article, "Geographic Coverage").startswith("{")
        else None,
        context=f"ARC article {article.get('id')}",
    )
    if geo.geographic_coverage:
        result["geographic_coverage"] = geo.geographic_coverage
    if geo.warnings:
        result["_geo_warnings"] = list(geo.warnings)

    return result


def _custom_field_list(article: dict[str, Any], field_name: str) -> list[str]:
    """Return list-valued custom field entries as strings."""
    for field in article.get("custom_fields") or []:
        if str(field.get("name") or "") != field_name:
            continue
        value = field.get("value")
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if value:
            return [str(value)]
    return []


def _text_suggests_gis(text: str) -> bool:
    """Return True when free text suggests a geospatial product."""
    blob = text.lower()
    return bool(re.search(
        r"\b(map|raster|vector|geotiff|shapefile|geodatabase|spatial|gis)\b",
        blob,
    ))
