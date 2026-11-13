"""
Map an EDG Clip and Ship feature to Storage metadata.

The summary is the Hub snippet followed by the first section of the full
description. Agency and office are the Environmental Protection Agency.
Feature layers are GIS data, and the time range is the published date through
the data-updated date.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup, Tag

from sourcing.EpaHubCandidateFetcher import row_from_feature
from sourcing.EpaSourcing import AGENCY
from utils.datalumos_data_types import DATA_TYPE_GIS
from utils.temporal_utils import pair_time_fields

_GEOSPATIAL_TYPES = {
    "feature service",
    "feature layer",
    "map service",
    "service definition",
}
_HEADING_TAGS = frozenset({"b", "strong"})
_BLOCK_TAGS = frozenset({"div", "p", "h1", "h2", "h3", "h4"})


def metadata_from_feature(
    feature: dict[str, Any],
    *,
    data_updated_ms: int | None = None,
) -> dict[str, Any]:
    """
    Map a Hub feature to Storage metadata fields.

    Args:
        feature: GeoJSON feature from the Clip and Ship catalog.
        data_updated_ms: Layer ``dataLastEditDate`` in epoch milliseconds.

    Returns:
        Title, summary, agency, office, keywords, data type, and time range.
    """
    row = row_from_feature(feature) or {}
    properties = feature.get("properties")
    props = properties if isinstance(properties, dict) else {}
    item_type = str(props.get("type") or "")
    fields: dict[str, Any] = {
        "title": row.get("title") or str(props.get("title") or "").strip(),
        "summary": _summary(props),
        "agency": AGENCY,
        "office": AGENCY,
        "keywords": _keywords(props.get("tags")),
    }
    if item_type.strip().casefold() in _GEOSPATIAL_TYPES:
        fields["data_types"] = DATA_TYPE_GIS
    fields.update(_time_fields(props.get("created"), data_updated_ms))
    return fields


def epoch_date(value: Any) -> str:
    """
    Return ``YYYY-MM-DD`` for an epoch timestamp in seconds or milliseconds.

    Args:
        value: Numeric epoch time.

    Returns:
        UTC date, or an empty string when ``value`` is not a timestamp.
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    if number < 10_000_000_000:
        number *= 1000
    moment = datetime.fromtimestamp(number / 1000, timezone.utc)
    return moment.date().isoformat()


def _summary(props: dict[str, Any]) -> str:
    """Keep the snippet, then the description's first section."""
    section = first_section_text(str(props.get("description") or ""))
    snippet = " ".join(str(props.get("snippet") or "").split())
    if not snippet or _fold(snippet) in _fold(section):
        return section or snippet
    if not section:
        return snippet
    return f"{snippet}\n\n{section}"


def _fold(text: str) -> str:
    """Collapse whitespace for a case-insensitive comparison."""
    return " ".join(text.casefold().split())


def first_section_text(html: str) -> str:
    """
    Return the description text before the first standalone heading.

    Inline bold stays in the paragraph. A block whose only content is a short
    bold title, such as ``About the AQI``, starts the next section.

    Args:
        html: Hub description HTML.

    Returns:
        Paragraphs joined by blank lines.
    """
    if not html.strip():
        return ""
    rendered = _render_section(BeautifulSoup(html, "html.parser"))
    paragraphs = [_clean_paragraph(block) for block in re.split(r"\n\s*\n", rendered)]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def _render_section(node: Any) -> str:
    """Render HTML until a section heading, keeping inline tags in the sentence."""
    chunks: list[str] = []
    for child in list(getattr(node, "children", [])):
        if isinstance(child, str):
            chunks.append(child)
            continue
        if not isinstance(child, Tag):
            continue
        if _is_section_heading(child):
            break
        if child.name == "br":
            chunks.append("\n")
            continue
        if child.name in _BLOCK_TAGS:
            chunks.append(f"\n\n{_render_section(child)}\n\n")
            continue
        chunks.append(_render_section(child))
    return "".join(chunks)


def _clean_paragraph(block: str) -> str:
    """Collapse whitespace and remove spaces before punctuation."""
    text = " ".join(block.split())
    return re.sub(r"\s+([.,;:)])", r"\1", text)


def _is_section_heading(element: Tag) -> bool:
    """Return True when ``element`` is only a short bold section title."""
    if element.name in {"h1", "h2", "h3", "h4"}:
        return True
    children = [
        child
        for child in element.children
        if not (isinstance(child, str) and not child.strip())
    ]
    if len(children) != 1 or not isinstance(children[0], Tag):
        return False
    if children[0].name not in _HEADING_TAGS:
        return False
    title = " ".join(children[0].get_text(" ", strip=True).split())
    return bool(title) and len(title) <= 80


def _time_fields(created: Any, data_updated_ms: int | None) -> dict[str, str]:
    """Pair the published date with the data-updated date."""
    start = epoch_date(created)
    end = epoch_date(data_updated_ms)
    if not start or not end:
        return {}
    return pair_time_fields(start, end)


def _keywords(tags: Any) -> str:
    """Join Hub tags into a comma-separated keyword string."""
    if isinstance(tags, str):
        return tags.strip()
    if not isinstance(tags, list):
        return ""
    values = [str(tag).strip() for tag in tags if str(tag).strip()]
    return ", ".join(values)
