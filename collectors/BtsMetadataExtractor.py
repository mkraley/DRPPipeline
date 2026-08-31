"""
Parse metadata and download links from ROSA P (BTS) dataset detail pages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from collectors.UsfsMetadataExtractor import parse_human_size
from sourcing.BtsCandidateFetcher import AGENCY, OFFICE
from utils.temporal_utils import pair_time_fields

_BTS_HOST = "rosap.ntl.bts.gov"
_VIEW_URL_RE = re.compile(r"/view/dot/(\d+)(?:/|$)")
_DS_FILE_RE = re.compile(r"_DS(\d+)\.([a-z0-9]+)$", re.IGNORECASE)
_FILE_SIZE_RE = re.compile(
    r"\[\s*([A-Z0-9]+)\s*-\s*([\d.,]+\s*(?:KB|MB|GB|TB|B))\s*\]",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PRESENT_END_DATE = "2026-01-01"
_PRESENT_RE = re.compile(r"\b(\d{4})\s*[-–]\s*Present\b", re.IGNORECASE)
_PRESENT_WORD_RE = re.compile(r"\bPresent\b", re.IGNORECASE)


@dataclass(frozen=True)
class BtsDownloadFile:
    """A main or supporting file listed on a ROSA P detail page."""

    label: str
    url: str
    filename: str
    size_bytes: int | None
    is_main: bool


def record_id_from_source_url(source_url: str) -> str | None:
    """
    Extract the numeric ROSA P record id from a view URL.

    Args:
        source_url: Portal URL (``.../view/dot/92758``).

    Returns:
        Record id string or None when the URL does not match.
    """
    match = _VIEW_URL_RE.search(source_url.strip())
    return match.group(1) if match else None


def parse_detail_page(html: str, page_url: str) -> dict[str, Any]:
    """
    Parse ROSA P detail HTML into Storage-oriented metadata fields.

    Args:
        html: Full page HTML from Playwright.
        page_url: Canonical source URL for resolving relative links.

    Returns:
        Metadata dict with title, summary, keywords, dates, and notes.
    """
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, Any] = {
        "agency": AGENCY,
        "office": OFFICE,
    }

    title_el = soup.select_one("h1#mainTitle")
    if title_el:
        result["title"] = title_el.get_text(" ", strip=True)

    publication_date = _publication_date(soup)
    label_values = _label_value_map(soup)
    summary = label_values.get("Abstract", "").strip()
    result.update(
        _temporal_range(
            result.get("title", ""),
            publication_date,
            summary,
        )
    )

    if summary:
        result["summary"] = summary

    keywords = _join_keywords(label_values)
    if keywords:
        result["keywords"] = keywords

    geographic = label_values.get("Geographical Coverage", "").strip()
    if geographic:
        result["geographic_coverage"] = _clean_geographic_coverage(geographic)

    notes = _build_collection_notes(label_values)
    if notes:
        result["collection_notes"] = notes

    format_label = label_values.get("Format", "").strip()
    data_types = infer_data_types(
        result.get("title", ""),
        result.get("summary", ""),
        keywords,
        format_label,
    )
    if data_types:
        result["data_types"] = data_types

    result["_format_label"] = format_label
    result["_main_size_bytes"] = _main_document_size_bytes(soup)
    result["_download_files"] = parse_download_files(html, page_url)
    return result


def parse_download_files(html: str, page_url: str) -> list[BtsDownloadFile]:
    """
    Extract main and supporting download links from a ROSA P detail page.

    Args:
        html: Full page HTML.
        page_url: Canonical source URL for resolving relative links.

    Returns:
        Deduplicated file entries with main/supporting classification.
    """
    soup = BeautifulSoup(html, "html.parser")
    record_id = record_id_from_source_url(page_url) or ""
    main_urls = _main_document_urls(soup, page_url, record_id)
    supporting = _supporting_files(soup, page_url, record_id)
    main_size = _main_document_size_bytes(soup)

    files: list[BtsDownloadFile] = []
    seen_urls: set[str] = set()

    for url in main_urls:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        filename = url.rsplit("/", 1)[-1]
        files.append(
            BtsDownloadFile(
                label="Main document",
                url=url,
                filename=filename,
                size_bytes=main_size if len(main_urls) == 1 else None,
                is_main=True,
            )
        )

    for entry in supporting:
        if entry.url in seen_urls:
            continue
        seen_urls.add(entry.url)
        files.append(entry)

    extra_main = _extra_main_documents(soup, page_url, record_id, seen_urls)
    for entry in extra_main:
        seen_urls.add(entry.url)
        files.append(entry)

    return files


def infer_data_types(
    title: str,
    summary: str,
    keywords: str,
    format_label: str,
    file_extensions: set[str] | frozenset[str] | None = None,
) -> str:
    """
    Infer DataLumos data types from BTS catalog text and archive extensions.

    Args:
        title: Dataset title.
        summary: Abstract text.
        keywords: Comma-separated subject terms.
        format_label: Format field value (e.g. ZIP).
        file_extensions: Optional extensions found inside downloaded archives.

    Returns:
        Semicolon-delimited data type labels, or an empty string.
    """
    blob = f"{title} {summary} {keywords} {format_label}".lower()
    types: list[str] = []
    normalized_exts = {
        str(ext).lstrip(".").lower()
        for ext in (file_extensions or set())
        if str(ext).strip()
    }
    gis_terms = (
        "geographic information",
        "gis",
        "shapefile",
        "geospatial",
        "spatial analysis",
        "transportation networks",
        "atlas database",
        "ntad",
        "layers",
    )
    gis_extensions = frozenset(
        {"shp", "shx", "dbf", "prj", "gpkg", "geojson", "kml", "kmz", "tif", "tiff"}
    )
    if any(term in blob for term in gis_terms) or normalized_exts & gis_extensions:
        types.append("GIS")
    tabular_terms = ("tabular", "spreadsheet", "database", "databases")
    tabular_extensions = frozenset(
        {"csv", "xlsx", "xls", "tsv", "dta", "sas7bdat", "parquet", "json"}
    )
    if any(term in blob for term in tabular_terms) or normalized_exts & tabular_extensions:
        types.append("tabular")
    if not types and format_label.upper() == "ZIP":
        types.append("other")
    return "; ".join(types)


def _publication_date(soup: BeautifulSoup) -> str:
    """Return YYYY-MM-DD from citation meta or the header date block."""
    meta = soup.find("meta", attrs={"name": "citation_publication_date"})
    if meta and meta.get("content"):
        raw = str(meta["content"]).strip().replace("/", "-")
        if _DATE_RE.match(raw):
            return raw
    for paragraph in soup.select("ul.bookHeaderList p"):
        text = paragraph.get_text(strip=True)
        if _DATE_RE.match(text):
            return text
    return ""


def _temporal_range(title: str, publication_date: str, summary: str = "") -> dict[str, str]:
    """
    Build ``time_start`` / ``time_end`` from title, abstract, and publication date.

    When catalog text mentions Present, ``time_end`` is set to ``2026-01-01``.
    Otherwise ``time_end`` defaults to ``time_start`` when only one bound is known.
    """
    combined = f"{title} {summary}".strip()
    present_match = _PRESENT_RE.search(combined)
    mentions_present = bool(present_match or _PRESENT_WORD_RE.search(combined))

    time_start = ""
    time_end = ""

    if present_match:
        time_start = f"{present_match.group(1)}-01-01"
        time_end = _PRESENT_END_DATE
    elif publication_date:
        time_start = publication_date
        time_end = publication_date

    paired = pair_time_fields(time_start or None, time_end or None)
    if mentions_present and paired.get("time_start"):
        paired["time_end"] = _PRESENT_END_DATE
    return paired


def _label_value_map(soup: BeautifulSoup) -> dict[str, str]:
    """Map Details section labels to plain-text values."""
    values: dict[str, str] = {}
    for row in soup.select("div.bookDetails li.bookDetails-row"):
        label_el = row.select_one(".bookDetailsLabel b")
        if label_el is None:
            continue
        label = label_el.get_text(" ", strip=True).rstrip(":")
        if not label or label in values:
            continue
        data_el = row.select_one(".bookDetailsData")
        if data_el is None:
            continue
        if label == "Abstract":
            values[label] = _abstract_text(data_el)
        else:
            values[label] = _link_list_text(data_el)
    return values


def _abstract_text(container: Tag) -> str:
    """
    Extract abstract text preserving paragraph breaks from ``<br>`` elements.

    ROSA P abstracts are plain text separated by ``<br/>`` pairs, not ``<p>`` tags.

    Args:
        container: ``.bookDetailsData`` element for the Abstract row.

    Returns:
        Paragraphs joined with blank lines.
    """
    fragment = BeautifulSoup(str(container), "html.parser")
    for br in fragment.find_all("br"):
        br.replace_with("\n")
    text = fragment.get_text()
    paragraphs = [
        part.strip()
        for part in re.split(r"\n\s*\n+", text)
        if part.strip()
    ]
    return "\n\n".join(paragraphs)


def _link_list_text(container: Tag) -> str:
    """Join anchor texts and plain text from a details value cell."""
    links = [anchor.get_text(" ", strip=True) for anchor in container.find_all("a")]
    if links:
        return "; ".join(link for link in links if link)
    return container.get_text(" ", strip=True)


def _join_keywords(label_values: dict[str, str]) -> str:
    """Combine subject terms and series into a keyword string."""
    parts: list[str] = []
    for key in ("Subject/TRT Terms", "Series"):
        value = label_values.get(key, "").strip()
        if value:
            parts.append(value)
    return "; ".join(parts)


def _build_collection_notes(label_values: dict[str, str]) -> str:
    """Build collection notes from DOI, creators, and checksum fields."""
    lines: list[str] = []
    for key in (
        "Alternative Title",
        "Corporate Creators",
        "Corporate Publisher",
        "DOI",
        "Main Document Checksum",
        "Collection(s)",
    ):
        value = label_values.get(key, "").strip()
        if value:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _clean_geographic_coverage(value: str) -> str:
    """Normalize ROSA P geographic coverage labels."""
    cleaned = value.strip()
    if cleaned.lower().startswith("usa use-"):
        cleaned = cleaned.split("-", 1)[-1].strip()
    return cleaned


def _absolute_url(href: str, page_url: str) -> str:
    """Resolve a possibly relative href against the page URL."""
    return urljoin(page_url, href.strip())


def _main_document_urls(soup: BeautifulSoup, page_url: str, record_id: str) -> list[str]:
    """Collect canonical main-document URLs from meta tags and download fields."""
    urls: list[str] = []
    meta = soup.find("meta", attrs={"name": "citation_pdf_url"})
    if meta and meta.get("content"):
        urls.append(_absolute_url(str(meta["content"]), page_url))

    for anchor in soup.select("#documentPDF a[href]"):
        urls.append(_absolute_url(anchor["href"], page_url))

    for button in soup.select("button.download-document-btn[data-file-url]"):
        urls.append(_absolute_url(str(button["data-file-url"]), page_url))

    if not urls and record_id:
        pattern = re.compile(rf"/view/dot/{re.escape(record_id)}/dot_{record_id}_DS\d+\.", re.I)
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if pattern.search(href):
                urls.append(_absolute_url(href, page_url))
                break

    return _dedupe_preserve_order(urls)


def _main_document_size_bytes(soup: BeautifulSoup) -> int | None:
    """Parse the main document size from the File Type row."""
    for row in soup.select("li.bookDetails-row.stacks-file-type"):
        text = row.get_text(" ", strip=True)
        match = _FILE_SIZE_RE.search(text)
        if not match:
            continue
        return parse_human_size(match.group(2))
    return None


def _supporting_files(
    soup: BeautifulSoup,
    page_url: str,
    record_id: str,
) -> list[BtsDownloadFile]:
    """Parse supporting file links from the Supporting Files tab."""
    files: list[BtsDownloadFile] = []
    for row in soup.select("ul.supporting-file li.bookDetails-row"):
        label_anchor = row.select_one("div.col-9 a[href], div.ps-0 a[href]")
        if label_anchor is None or not label_anchor.get("href"):
            continue
        href = _absolute_url(label_anchor["href"], page_url)
        if record_id and f"/view/dot/{record_id}/" not in href:
            continue
        label = label_anchor.get_text(" ", strip=True) or "Supporting file"
        filename = href.rsplit("/", 1)[-1]
        files.append(
            BtsDownloadFile(
                label=label,
                url=href,
                filename=filename,
                size_bytes=None,
                is_main=False,
            )
        )
    return files


def _extra_main_documents(
    soup: BeautifulSoup,
    page_url: str,
    record_id: str,
    seen_urls: set[str],
) -> list[BtsDownloadFile]:
    """
    Detect additional main documents beyond the primary DS1 link.

    Some records expose multiple dataset files outside the Supporting Files tab.
    """
    if not record_id:
        return []

    extras: list[BtsDownloadFile] = []
    pattern = re.compile(rf"/view/dot/{re.escape(record_id)}/dot_{record_id}_DS\d+\.", re.I)
    for anchor in soup.select("div.bookDetails a[href]"):
        href = anchor.get("href", "")
        if not pattern.search(href):
            continue
        url = _absolute_url(href, page_url)
        if url in seen_urls:
            continue
        if anchor.find_parent("ul", class_="supporting-file"):
            continue
        ds_match = _DS_FILE_RE.search(url)
        if ds_match and int(ds_match.group(1)) <= 1:
            continue
        label = anchor.get_text(" ", strip=True) or url.rsplit("/", 1)[-1]
        if label.lower() == "download":
            continue
        extras.append(
            BtsDownloadFile(
                label=label,
                url=url,
                filename=url.rsplit("/", 1)[-1],
                size_bytes=None,
                is_main=True,
            )
        )
        seen_urls.add(url)
    return extras


def _dedupe_preserve_order(urls: list[str]) -> list[str]:
    """Return unique URLs while preserving first-seen order."""
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique
