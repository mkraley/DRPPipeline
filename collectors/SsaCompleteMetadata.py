"""Parse catalog.data.gov Complete Metadata (DCAT table)."""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup, Tag

from collectors.SsaCatalogJsonLd import geographic_label, temporal_fields
from utils.temporal_utils import pair_time_fields

COMPLETE_METADATA_HEADING_SELECTOR = "h2.complete-metadata-heading"


def coverage_from_complete_metadata(soup: BeautifulSoup) -> dict[str, str]:
    """
    Return temporal and geographic fields from the Complete Metadata table.

    Args:
        soup: Parsed catalog dataset page.

    Returns:
        Any of ``time_start``, ``time_end``, and ``geographic_coverage``.
    """
    rows = complete_metadata_rows(soup)
    result: dict[str, str] = {}
    geographic = geographic_from_metadata_value(rows.get("spatial"))
    if geographic:
        result["geographic_coverage"] = geographic
    result.update(temporal_from_metadata_value(rows.get("temporal")))
    return result


def complete_metadata_rows(soup: BeautifulSoup) -> dict[str, Any]:
    """
    Parse Complete Metadata table cells into a name-to-value map.

    Args:
        soup: Parsed catalog dataset page.

    Returns:
        DCAT field names mapped to JSON values or plain text.
    """
    heading = soup.select_one(COMPLETE_METADATA_HEADING_SELECTOR)
    if heading is None:
        return {}
    details = heading.find_parent("details")
    table = details.select_one("table.metadata-table") if details else None
    if table is None:
        return {}
    parsed: dict[str, Any] = {}
    for row in table.select("tr"):
        header = row.find("th")
        cell = row.find("td")
        if not isinstance(header, Tag) or not isinstance(cell, Tag):
            continue
        key = header.get_text(" ", strip=True)
        if key:
            parsed[key] = _cell_value(cell)
    return parsed


def temporal_from_metadata_value(raw: Any) -> dict[str, str]:
    """
    Build time_start/time_end from a Complete Metadata temporal cell.

    Args:
        raw: Parsed JSON (PeriodOfTime list/dict) or a coverage string.

    Returns:
        Paired temporal fields, or empty when the cell is missing.
    """
    if raw is None or raw == "":
        return {}
    if isinstance(raw, list) and raw:
        return temporal_from_metadata_value(raw[0])
    if isinstance(raw, dict):
        start = str(raw.get("startDate") or raw.get("start") or "").strip()
        end = str(raw.get("endDate") or raw.get("end") or "").strip()
        return pair_time_fields(start, end)
    if isinstance(raw, str):
        return temporal_fields("", {"temporal": raw})
    return {}


def geographic_from_metadata_value(raw: Any) -> str:
    """
    Build a place label from a Complete Metadata spatial cell.

    Args:
        raw: Parsed JSON (Location list/dict) or a plain string.

    Returns:
        Geographic coverage text, or empty when missing.
    """
    return geographic_label(raw)


def _cell_value(cell: Tag) -> Any:
    """Parse a table cell as JSON when possible."""
    text = _cell_text(cell)
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _cell_text(cell: Tag) -> str:
    """Prefer pretty-printed JSON in ``<pre>``, else the cell's text."""
    pre = cell.select_one("pre.json, pre")
    if pre is not None:
        return pre.get_text("\n", strip=True)
    return cell.get_text(" ", strip=True)
