"""JSON-LD helpers for catalog.data.gov SSA dataset pages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from sourcing.SsaCandidateFetcher import FILE_SUFFIXES
from utils.temporal_utils import extract_dates_from_text, pair_time_fields

_TEMPORAL_SPLIT_RE = re.compile(r"[/,]")
_MIME_TO_FORMAT = {
    "application/zip": "ZIP",
    "application/pdf": "PDF",
    "text/csv": "CSV",
    "application/json": "JSON",
    "application/xml": "XML",
    "text/xml": "XML",
    "text/html": "HTML",
    "application/vnd.ms-excel": "XLS",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
    "text/plain": "TXT",
}


def json_ld_dataset(soup: BeautifulSoup) -> dict[str, Any]:
    """Return the first schema.org Dataset object embedded in the page."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        dataset = _first_dataset(payload)
        if dataset:
            return dataset
    return {}


def json_ld_downloads(dataset: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Return (label, url, format) tuples from JSON-LD distributions."""
    rows: list[tuple[str, str, str]] = []
    distributions = dataset.get("distribution") or []
    if isinstance(distributions, dict):
        distributions = [distributions]
    if not isinstance(distributions, list):
        return rows
    for index, dist in enumerate(distributions, 1):
        if not isinstance(dist, dict):
            continue
        url = str(dist.get("contentUrl") or dist.get("downloadURL") or "").strip()
        if not url:
            continue
        fmt = format_from_encoding(str(dist.get("encodingFormat") or dist.get("format") or ""), url)
        label = str(dist.get("name") or dist.get("title") or f"Resource {index}").strip()
        rows.append((label, url, fmt))
    return rows


def page_title(soup: BeautifulSoup, dataset: dict[str, Any]) -> str:
    """Prefer the visible heading, then JSON-LD name."""
    heading = soup.find("h1")
    if isinstance(heading, Tag):
        text = heading.get_text(" ", strip=True)
        if text:
            return text
    return str(dataset.get("name") or "").strip()


def page_summary(soup: BeautifulSoup, dataset: dict[str, Any]) -> str:
    """Prefer JSON-LD description, then the first prose paragraph."""
    description = str(dataset.get("description") or "").strip()
    if description:
        return description
    prose = soup.select_one("p.usa-prose, p.usa-collection__description")
    if prose:
        return prose.get_text(" ", strip=True)
    return ""


def page_keywords(dataset: dict[str, Any]) -> str:
    """Join JSON-LD keywords into a comma-separated string."""
    raw = dataset.get("keywords") or dataset.get("keyword")
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts = [str(item).strip() for item in raw if str(item).strip()]
        return ", ".join(parts)
    return ""


def page_geographic(dataset: dict[str, Any]) -> str:
    """Extract a place label from JSON-LD spatial."""
    return geographic_label(dataset.get("spatial") or dataset.get("spatialCoverage"))


def geographic_label(spatial: Any) -> str:
    """
    Flatten a DCAT/JSON-LD spatial value into a place label.

    Args:
        spatial: String, Location dict, or list of those.

    Returns:
        Comma-separated labels, or empty when none are present.
    """
    if isinstance(spatial, list):
        labels = [geographic_label(item) for item in spatial]
        return ", ".join(part for part in labels if part)
    if isinstance(spatial, str):
        return spatial.strip()
    if isinstance(spatial, dict):
        return str(spatial.get("name") or spatial.get("prefLabel") or "").strip()
    return ""


def temporal_fields(title: str, dataset: dict[str, Any]) -> dict[str, str]:
    """Build time_start/time_end from JSON-LD coverage or the title."""
    coverage = str(dataset.get("temporalCoverage") or dataset.get("temporal") or "")
    start = ""
    end = ""
    if coverage:
        parts = [part.strip() for part in _TEMPORAL_SPLIT_RE.split(coverage) if part.strip()]
        if parts:
            start = parts[0]
        if len(parts) >= 2:
            end = parts[-1]
    if not start:
        dates = extract_dates_from_text(title)
        if dates:
            start = min(dates)
            end = max(dates)
    return pair_time_fields(start, end)


def format_from_encoding(encoding: str, url: str) -> str:
    """Map a MIME type or URL suffix to a short format token."""
    encoding_lower = encoding.lower()
    if encoding_lower in _MIME_TO_FORMAT:
        return _MIME_TO_FORMAT[encoding_lower]
    if encoding.strip():
        token = encoding.strip().split("/")[-1].upper()
        if token:
            return token
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in FILE_SUFFIXES:
        return suffix.lstrip(".").upper()
    if suffix in {".html", ".htm"}:
        return "HTML"
    return ""


def _first_dataset(payload: Any) -> dict[str, Any] | None:
    """Find a Dataset dict in a JSON-LD payload."""
    if isinstance(payload, dict):
        type_value = payload.get("@type")
        types = type_value if isinstance(type_value, list) else [type_value]
        if any(str(item).endswith("Dataset") for item in types if item):
            return payload
        graph = payload.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                found = _first_dataset(item)
                if found:
                    return found
    if isinstance(payload, list):
        for item in payload:
            found = _first_dataset(item)
            if found:
                return found
    return None
