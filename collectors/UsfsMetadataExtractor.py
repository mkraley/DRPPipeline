"""
Parse metadata from USFS Research Data Archive catalog detail and FGDC pages.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

AGENCY = "US Department of Agriculture"
OFFICE = "US Forest Service"
SITE_BASE = "https://www.fs.usda.gov"
RDS_ID_RE = re.compile(r"(RDS-\d{4}-\d{4})")
DOWNLOAD_COUNT_RE = re.compile(r"Download count:\s*(\d+)", re.IGNORECASE)
SKIP_PRESENTATION_FORMS = frozenset({"journal article", "document", "software"})


def rds_id_from_source_url(source_url: str) -> str | None:
    """Extract RDS-YYYY-NNNN from a catalog or product URL."""
    match = RDS_ID_RE.search(source_url)
    return match.group(1) if match else None


def metadata_url_for_rds_id(rds_id: str) -> str:
    """Build the FGDC metadata HTML URL for a catalog RDS identifier."""
    return f"{SITE_BASE}/rds/archive/products/{rds_id}/_metadata_{rds_id}.html"


def fileindex_url_for_rds_id(rds_id: str) -> str:
    """Build the file index HTML URL for a catalog RDS identifier."""
    return f"{SITE_BASE}/rds/archive/products/{rds_id}/_fileindex_{rds_id}.html"


def parse_data_access_links(html: str, base_url: str) -> dict[str, Any]:
    """
    Parse Data Access links from a catalog detail page.

    Returns:
        Dict with metadata_url, fileindex_url, and publication_files
        (list of ``(filename, absolute_url)`` tuples).
    """
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, Any] = {
        "metadata_url": "",
        "fileindex_url": "",
        "publication_files": [],
    }

    for dt in soup.find_all("dt"):
        if "Data Access" not in dt.get_text():
            continue
        dd = dt.find_next_sibling("dd")
        if not dd:
            break

        for anchor in dd.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href or href == "#":
                continue
            label = anchor.get_text(strip=True)
            label_lower = label.lower()
            absolute = urljoin(base_url, href)

            if label_lower == "metadata":
                result["metadata_url"] = absolute
            elif label_lower == "file index":
                result["fileindex_url"] = absolute
            elif "/rds/archive/products/" in href and not href.endswith(".html"):
                result["publication_files"].append((label, absolute))
        break

    return result


def parse_def_list(html: str) -> dict[str, str]:
    """Parse ``<dt>/<dd>`` pairs from catalog detail HTML."""
    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}
    for dt in soup.find_all("dt"):
        key = dt.get_text(strip=True).rstrip(":")
        dd = dt.find_next_sibling("dd")
        if dd:
            fields[key] = dd.get_text(" ", strip=True)
    return fields


def parse_download_count(metrics_text: str) -> int | None:
    """Extract download count from the Metrics field text."""
    match = DOWNLOAD_COUNT_RE.search(metrics_text or "")
    return int(match.group(1)) if match else None


def normalize_keywords(raw: str) -> str:
    """Convert semicolon-separated catalog keywords to comma-separated."""
    if not raw:
        return ""
    parts = [part.strip() for part in raw.split(";") if part.strip()]
    return ", ".join(parts)


def infer_data_types(presentation_form: str) -> str:
    """Map FGDC presentation form to DataLumos-style data type."""
    form = presentation_form.lower()
    if "raster" in form or "vector" in form:
        return "geospatial"
    if "tabular" in form or "database" in form:
        return "tabular"
    return "other"


def parse_detail_page(html: str, source_url: str) -> dict[str, Any]:
    """Extract metadata available on the catalog detail page."""
    fields = parse_def_list(html)
    soup = BeautifulSoup(html, "html.parser")

    title = fields.get("Title", "")
    summary = fields.get("Abstract", "")
    keywords = normalize_keywords(fields.get("Keywords", ""))
    authors = fields.get("Author(s)", "")
    pub_year = fields.get("Publication Year", "")
    metrics = fields.get("Metrics", "")
    downloads = parse_download_count(metrics)

    doi = ""
    doi_meta = soup.find("meta", attrs={"name": "citation_doi"})
    if doi_meta and doi_meta.get("content"):
        doi = doi_meta["content"].strip()

    notes_parts: list[str] = []
    if doi:
        notes_parts.append(f"DOI: {doi}")
    if authors:
        notes_parts.append(f"Authors: {authors}")
    if pub_year:
        notes_parts.append(f"Publication year: {pub_year}")

    result: dict[str, Any] = {
        "title": title,
        "summary": summary,
        "keywords": keywords,
        "agency": AGENCY,
        "office": OFFICE,
        "collection_notes": "\n".join(notes_parts),
    }
    if downloads is not None:
        result["downloads"] = downloads
    if pub_year and not result.get("time_end"):
        result["time_end"] = pub_year
    return result


def parse_metadata_page(html: str) -> dict[str, Any]:
    """Extract supplemental metadata from the FGDC metadata HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, Any] = {}

    presentation_forms: list[str] = []
    beginning_date = ""
    ending_date = ""

    for dt in soup.find_all("dt"):
        text = dt.get_text(strip=True)
        if text.startswith("Geospatial_Data_Presentation_Form:"):
            form = text[len("Geospatial_Data_Presentation_Form:") :].strip()
            if form:
                presentation_forms.append(form)
        elif text == "Beginning_Date:" or text.startswith("Beginning_Date:"):
            if not beginning_date:
                beginning_date = text.split(":", 1)[1].strip() if ":" in text else ""
        elif text == "Ending_Date:" or text.startswith("Ending_Date:"):
            if not ending_date:
                ending_date = text.split(":", 1)[1].strip() if ":" in text else ""

    if beginning_date:
        result["time_start"] = beginning_date
    if ending_date:
        result["time_end"] = ending_date

    for form in presentation_forms:
        if form.lower() not in SKIP_PRESENTATION_FORMS:
            result["data_types"] = infer_data_types(form)
            break

    return result


def merge_usfs_metadata(detail: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    """Merge detail-page and FGDC metadata, preferring richer values."""
    merged = {**detail}
    for key, value in metadata.items():
        if value is None or value == "":
            continue
        if key not in merged or not merged.get(key):
            merged[key] = value
        elif key in ("time_start", "time_end", "data_types"):
            merged[key] = value
    return merged
