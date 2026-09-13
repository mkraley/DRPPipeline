"""
Parse metadata and file downloads from catalog.data.gov SSA dataset pages.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, Tag

from collectors.BtsMetadataExtractor import infer_data_types
from collectors.SsaCatalogJsonLd import (
    format_from_encoding,
    json_ld_dataset,
    json_ld_downloads,
    page_geographic,
    page_keywords,
    page_summary,
    page_title,
    temporal_fields,
)
from collectors.SsaCompleteMetadata import coverage_from_complete_metadata
from sourcing.SsaCandidateFetcher import AGENCY, OFFICE, is_file_download, is_html_url


@dataclass(frozen=True)
class SsaDownloadFile:
    """A download or HTML resource listed on an SSA catalog dataset page."""

    label: str
    url: str
    filename: str
    size_bytes: int | None = None


def parse_catalog_page(html: str, page_url: str) -> dict[str, Any]:
    """
    Parse a catalog.data.gov dataset page into Storage-oriented fields.

    Args:
        html: Catalog dataset HTML.
        page_url: Canonical source URL.

    Returns:
        Metadata dict plus ``_download_files``, ``_html_resources``,
        and ``_format_label``.
    """
    soup = BeautifulSoup(html, "html.parser")
    dataset = json_ld_dataset(soup)
    result: dict[str, Any] = {"agency": AGENCY, "office": OFFICE}

    title = page_title(soup, dataset)
    if title:
        result["title"] = title
    summary = page_summary(soup, dataset)
    if summary:
        result["summary"] = summary
    keywords = page_keywords(dataset)
    if keywords:
        result["keywords"] = keywords
    complete = coverage_from_complete_metadata(soup)
    geographic = complete.get("geographic_coverage") or page_geographic(dataset)
    if geographic:
        result["geographic_coverage"] = geographic

    if complete.get("time_start") or complete.get("time_end"):
        result.update(
            {
                key: complete[key]
                for key in ("time_start", "time_end")
                if complete.get(key)
            }
        )
    else:
        result.update(temporal_fields(title, dataset))
    identifier = str(dataset.get("identifier") or "").strip()
    if identifier:
        result["collection_notes"] = f"Identifier: {identifier}"

    files = parse_download_files(html, page_url)
    result["_html_resources"] = parse_html_resources(html, page_url)
    formats = sorted({Path(entry.filename).suffix.lstrip(".").upper() for entry in files})
    format_label = ", ".join(formats)
    result["_format_label"] = format_label
    result["_download_files"] = files
    data_types = infer_data_types(
        result.get("title", ""),
        result.get("summary", ""),
        result.get("keywords", ""),
        format_label,
    )
    if data_types:
        result["data_types"] = data_types
    return result


def parse_download_files(html: str, page_url: str) -> list[SsaDownloadFile]:
    """
    Collect non-HTML download URLs from JSON-LD and the Resources list.

    Args:
        html: Catalog dataset HTML.
        page_url: Unused; kept for call-site symmetry with other extractors.

    Returns:
        Deduplicated file entries in page order.
    """
    del page_url
    return _entries_from_candidates(_resource_candidates(html), html_resources=False)


def parse_html_resources(html: str, page_url: str) -> list[SsaDownloadFile]:
    """
    Collect HTML landing-page URLs from JSON-LD and the Resources list.

    Args:
        html: Catalog dataset HTML.
        page_url: Unused; kept for call-site symmetry with other extractors.

    Returns:
        Deduplicated HTML resource entries in page order.
    """
    del page_url
    return _entries_from_candidates(_resource_candidates(html), html_resources=True)


def _resource_candidates(html: str) -> list[tuple[str, str, str]]:
    """Return (label, url, format) tuples from JSON-LD and the Resources list."""
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[str, str, str]] = []
    candidates.extend(json_ld_downloads(json_ld_dataset(soup)))
    candidates.extend(_resource_list_downloads(soup))
    return candidates


def _entries_from_candidates(
    candidates: list[tuple[str, str, str]],
    html_resources: bool,
) -> list[SsaDownloadFile]:
    """Filter resource tuples into download files or HTML landing pages."""
    files: list[SsaDownloadFile] = []
    seen: set[str] = set()
    for label, url, fmt in candidates:
        if url in seen:
            continue
        is_html = is_html_url(url, fmt)
        is_file = is_file_download({"format": fmt, "downloadURL": url})
        if html_resources and not is_html:
            continue
        if not html_resources and not is_file:
            continue
        seen.add(url)
        files.append(
            SsaDownloadFile(
                label=label or filename_from_url(url),
                url=url,
                filename=filename_from_url(url),
            )
        )
    return files


def filename_from_url(url: str) -> str:
    """
    Return a basename from a download URL.

    Args:
        url: Absolute file URL.

    Returns:
        Decoded path tail, or ``download`` when missing.
    """
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1]).strip()
    return name or "download"


def _resource_list_downloads(soup: BeautifulSoup) -> list[tuple[str, str, str]]:
    """Return (label, url, format) tuples from the Resources list."""
    rows: list[tuple[str, str, str]] = []
    for item in soup.select("li.resources-list__item"):
        link = item.select_one("a.resources-list__btn[href], a[href]")
        if not isinstance(link, Tag):
            continue
        url = str(link.get("href") or "").strip()
        if not url:
            continue
        fmt_el = item.select_one(".resources-list__format")
        fmt = fmt_el.get_text(" ", strip=True) if fmt_el else ""
        name_el = item.select_one(".resources-list__name")
        label = name_el.get_text(" ", strip=True) if name_el else filename_from_url(url)
        rows.append((label, url, fmt or format_from_encoding("", url)))
    return rows
