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
CATALOG_ID_RE = re.compile(r"([A-Z]{2,4}-\d{4}-\d{3,4})")
DOWNLOAD_COUNT_RE = re.compile(r"Download count:\s*(\d+)", re.IGNORECASE)
_PUBLICATION_FILE_EXTENSIONS = (
    ".zip",
    ".csv",
    ".xlsx",
    ".xls",
    ".gz",
    ".tar",
    ".tif",
    ".tiff",
)
_SIZE_IN_EM_RE = re.compile(
    r"\(\s*([\d.,]+\s*(?:KB|MB|GB|TB|B))\s*;",
    re.IGNORECASE,
)
_SIZE_TOKEN_RE = re.compile(
    r"^([\d.,]+)\s*(B|KB|MB|GB|TB)\s*$",
    re.IGNORECASE,
)
_SIZE_MULTIPLIERS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
    "TB": 1024**4,
}


def parse_human_size(text: str) -> int | None:
    """Parse a catalog size string such as ``30.8 GB`` or ``26.25 KB`` to bytes."""
    match = _SIZE_TOKEN_RE.match(text.strip())
    if not match:
        return None
    num = float(match.group(1).replace(",", ""))
    unit = match.group(2).upper()
    return int(num * _SIZE_MULTIPLIERS[unit])


def _catalog_size_bytes_for_anchor(anchor) -> int | None:
    """Read ``(NNN MB;`` from the ``<em>`` sibling on the catalog detail page."""
    li = anchor.find_parent("li")
    if not li:
        return None
    em = li.find("em")
    if not em:
        return None
    match = _SIZE_IN_EM_RE.search(em.get_text())
    if not match:
        return None
    return parse_human_size(match.group(1))


def _is_publication_download_link(label: str, href: str) -> bool:
    """True if anchor is a downloadable publication file (not metadata/index/checksum)."""
    if not href or href == "#":
        return False
    label_lower = label.strip().lower()
    if label_lower in ("metadata", "file index", "checksum"):
        return False
    if any(label_lower.endswith(ext) for ext in _PUBLICATION_FILE_EXTENSIONS):
        return True
    if "/rds/archive/products/" in href and not href.endswith(".html"):
        return True
    return False


def rds_id_from_source_url(source_url: str) -> str | None:
    """Extract publication id (e.g. RDS-2026-0018 or EFR-2026-001) from a catalog URL."""
    match = CATALOG_ID_RE.search(source_url)
    return match.group(1) if match else None


def normalize_temporal_date(value: str) -> str:
    """
    Normalize FGDC-style dates for storage.

    - 4 digits (year): unchanged, e.g. ``1987``
    - 6 digits (YYYYMM): ``201606`` -> ``2016-06-01``
    - 8 digits (YYYYMMDD): ``19990803`` -> ``1999-08-03``
    - Already ISO-like values are left unchanged when not all digits.
    """
    if not value:
        return ""
    raw = value.strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 4 and digits.isdigit():
        return digits
    if len(digits) == 6 and digits.isdigit():
        return f"{digits[:4]}-{digits[4:6]}-01"
    if len(digits) == 8 and digits.isdigit():
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return raw


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
        (list of ``(filename, absolute_url, size_bytes)`` tuples; size from catalog HTML).
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
            elif _is_publication_download_link(label, href):
                size_bytes = _catalog_size_bytes_for_anchor(anchor)
                result["publication_files"].append((label, absolute, size_bytes))
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


def clean_keyword_token(token: str) -> str:
    """Strip whitespace and leading/trailing ampersands from one keyword token."""
    return token.strip().strip("&").strip()


def split_keywords(raw: str) -> list[str]:
    """Split on commas or semicolons and clean each keyword token."""
    if not raw:
        return []
    parts = re.split(r"[,;]+", raw)
    return [cleaned for p in parts if (cleaned := clean_keyword_token(p))]


def normalize_keywords(raw: str) -> str:
    """Split USFS keywords on commas/semicolons, clean tokens, join with commas."""
    return ", ".join(split_keywords(raw))


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
        result["time_end"] = normalize_temporal_date(pub_year)
    return result


def _dt_label(dt) -> str:
    """Normalize a metadata ``<dt>`` label (text before the first colon)."""
    return dt.get_text(strip=True).split(":", 1)[0].strip()


_EXTENT_TRUNCATE_MARKERS = (
    "http://",
    "https://",
    "doi.org",
    "Author Information:",
    "Originator:",
)


def _dd_text_after_dt(dt) -> str:
    dd = dt.find_next_sibling("dd")
    if not dd:
        return ""
    # Use only content before the first <br> (citations often follow).
    chunks: list[str] = []
    for child in dd.children:
        name = getattr(child, "name", None)
        if name in ("br", "a"):
            break
        if name is None:
            piece = str(child).strip()
            if piece:
                chunks.append(piece)
        else:
            chunks.append(child.get_text(" ", strip=True))
    text = " ".join(c for c in chunks if c).strip()
    if not text:
        text = dd.get_text(" ", strip=True)
    for marker in _EXTENT_TRUNCATE_MARKERS:
        if marker in text:
            text = text.split(marker, 1)[0].strip()
    return text


def _parse_coordinate_value(text: str) -> float | None:
    if not text:
        return None
    cleaned = text.strip().replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_metadata_page(html: str) -> dict[str, Any]:
    """Extract supplemental metadata from the FGDC metadata HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, Any] = {}

    beginning_date = ""
    ending_date = ""
    geographic_extent = ""
    place_keywords: list[str] = []
    bbox: dict[str, float] = {}

    for dt in soup.find_all("dt"):
        label = _dt_label(dt)
        if label == "Beginning_Date" or label.startswith("Beginning_Date"):
            if not beginning_date:
                beginning_date = dt.get_text(strip=True).split(":", 1)[-1].strip()
        elif label == "Ending_Date" or label.startswith("Ending_Date"):
            if not ending_date:
                ending_date = dt.get_text(strip=True).split(":", 1)[-1].strip()
        elif label == "Description_of_Geographic_Extent":
            if not geographic_extent:
                geographic_extent = _dd_text_after_dt(dt)
        elif label == "Place_Keyword" or "Place_Keyword" in dt.get_text():
            raw = dt.get_text(strip=True)
            kw = raw.split("Place_Keyword", 1)[-1].lstrip(": ").strip()
            if kw and not kw.startswith("_") and "Thesaurus" not in kw:
                place_keywords.append(kw)
        elif label in (
            "West_Bounding_Coordinate",
            "East_Bounding_Coordinate",
            "North_Bounding_Coordinate",
            "South_Bounding_Coordinate",
        ):
            parts = dt.get_text(strip=True).split(":", 1)
            val = _parse_coordinate_value(parts[-1] if len(parts) > 1 else "")
            if val is not None:
                key = label.split("_", 1)[0].lower()
                bbox[key] = val

    if beginning_date:
        result["time_start"] = normalize_temporal_date(beginning_date)
    if ending_date:
        result["time_end"] = normalize_temporal_date(ending_date)
    if geographic_extent:
        result["geographic_extent_description"] = geographic_extent
    if place_keywords:
        result["place_keywords"] = place_keywords
    if len(bbox) == 4:
        result["bounding_box"] = bbox

    return result


# DataLumos kindOfData controlled vocabulary (exact checklist labels).
DATA_TYPE_ADMINISTRATIVE = "Administrative records data"
DATA_TYPE_AGGREGATE = "Aggregate data"
DATA_TYPE_EXPERIMENTAL = "Experimental data"
DATA_TYPE_GIS = "Geographic information system (GIS) data"
DATA_TYPE_OBSERVATIONAL = "Observational data"
DATA_TYPE_PROGRAM_SOURCE = "Program source code"
DATA_TYPE_SURVEY = "Survey data"

_GIS_TEXT_PATTERNS = (
    r"\braster\b",
    r"\bgeotiff\b",
    r"\bgeo[- ]?tiff\b",
    r"\bshapefile\b",
    r"\bgeodatabase\b",
    r"\bspatial database\b",
    r"\bvector digital map\b",
    r"\bgeoreferenced\b.*\btiff\b",
    r"\btiff files?\b.*\bbands?\b",
    r"\bimputed map\b",
    r"\bprediction maps\b",
    r"\bspatial datasets?\b",
    r"\braster layers?\b",
    r"\braster datasets?\b",
)
_AGGREGATE_TEXT_PATTERNS = (
    r"\btables of estimates\b",
    r"\bestimate tables\b",
    r"\bstandard .*?estimate tables\b",
    r"\bstandard state-level\b",
    r"\bfiadb\b.*\btables\b",
    r"\bcompiled each year\b.*\bestimates\b",
    r"\bpre-computed\b.*\btables\b",
)
_OBSERVATIONAL_TEXT_PATTERNS = (
    r"\bcollected\b",
    r"\bsampled\b",
    r"\bmeasured\b",
    r"\bobservations?\b",
    r"\bfield (?:data|measurements|sampling)\b",
    r"\bfloristic inventories\b",
    r"\bvegetation (?:surveyed|inventory)\b",
    r"\bbenthic\b",
    r"\bmacroinvertebrate\b",
    r"\bplot(?:s|-level)\b",
    r"\bbiweekly\b",
    r"\bhourly samples?\b",
    r"\bpollinator\b.*\bdata\b",
)
_SURVEY_TEXT_PATTERNS = (
    r"\bvisitor survey\b",
    r"\bsurvey data collected\b",
    r"\bquestionnaire\b",
    r"\brespondents?\b",
    r"\bdemographics\b",
)
_PROGRAM_SOURCE_TEXT_PATTERNS = (
    r"\bstata code\b",
    r"\br scripts?\b",
    r"\bgoogle earth engine\b",
    r"\bprogram code\b",
    r"\breplicate a study\b",
)
_ADMINISTRATIVE_TEXT_PATTERNS = (
    r"\bsuppression spending data\b",
    r"\bhistorical monthly input data\b",
)
_EXPERIMENTAL_TEXT_PATTERNS = (
    r"\bexperimental burn units?\b",
    r"\btreatment units?\b",
    r"\bgrowing stock levels?\b.*\bplots?\b",
    r"\bplant succession study\b",
)
_ARCHIVAL_DOCUMENTS_PATTERN = re.compile(
    r"\bhistorical documents\b.*\b(?:letters|reports|notes|memorandums)\b",
    re.IGNORECASE | re.DOTALL,
)
_RAW_OR_PLOT_DATA_PATTERN = re.compile(
    r"\braw data\b|\bplot[- ]level\b|\bfield measurements\b|\btree inventories\b",
    re.IGNORECASE,
)


def parse_data_type_signals(html: str) -> dict[str, Any]:
    """Extract FGDC metadata signals useful for DataLumos data-type inference."""
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    signals: dict[str, Any] = {
        "direct_spatial_raster": False,
        "direct_spatial_vector": False,
        "format_names": [],
        "presentation_forms": [],
        "entity_overview": "",
    }

    for dt in soup.find_all("dt"):
        label = _dt_label(dt)
        text = dt.get_text(" ", strip=True)
        label_lower = label.lower()

        if label.startswith("Direct_Spatial_Reference_Method"):
            method = text.split(":", 1)[-1].strip().lower()
            if "raster" in method:
                signals["direct_spatial_raster"] = True
            if "vector" in method:
                signals["direct_spatial_vector"] = True
        elif label.startswith("Geospatial_Data_Presentation_Form"):
            form = text.split(":", 1)[-1].strip().lower()
            if form:
                signals["presentation_forms"].append(form)
        elif label.startswith("Format_Name"):
            fmt = text.split(":", 1)[-1].strip()
            if fmt:
                signals["format_names"].append(fmt)
        elif "Entity_and_Attribute_Overview" in label and not signals["entity_overview"]:
            dd = dt.find_next_sibling("dd")
            if dd:
                signals["entity_overview"] = dd.get_text(" ", strip=True).lower()

    return signals


def _text_matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _signals_indicate_gis(signals: dict[str, Any], text_blob: str = "") -> bool:
    if signals.get("direct_spatial_raster") or signals.get("direct_spatial_vector"):
        return True

    overview = signals.get("entity_overview", "")
    if overview and _text_matches_any(
        overview,
        (r"\braster\b", r"\bgeotiff\b", r"\bshapefile\b", r"\bgeodatabase\b"),
    ):
        return True

    gis_formats = {"gdb", "tiff", "shp", "shapefile"}
    if overview:
        for fmt in signals.get("format_names", []):
            fmt_lower = fmt.lower()
            if any(token in fmt_lower for token in gis_formats):
                return True
            if "georeferenced" in fmt_lower and "tiff" in fmt_lower:
                return True

    return False


def _gis_primary_product(blob: str) -> bool:
    """True when the published product is primarily spatial rather than field observations."""
    return _text_matches_any(
        blob,
        (
            r"\bimputed map\b",
            r"\bdata publication contains a spatial\b",
            r"\braster datasets?\b",
            r"\braster layers?\b",
            r"\bgeoreferenced\b",
            r"\bshapefile\b",
            r"\bgeodatabase\b",
            r"\bspatial database\b",
            r"\bgeo[- ]?tiff\b",
            r"\btiff files\b",
            r"\bvector digital map\b",
        ),
    )


def _signals_indicate_program_source(signals: dict[str, Any]) -> bool:
    for fmt in signals.get("format_names", []):
        fmt_upper = fmt.upper()
        if fmt_upper in {"DO", "R", "JS", "PY", "JAVA"}:
            return True
        if "code" in fmt.lower() or "script" in fmt.lower():
            return True
    return False


def infer_data_types(title: str, summary: str, metadata_html: str = "") -> str:
    """
    Infer DataLumos data type(s) from catalog title, abstract, and FGDC metadata.

    Returns semicolon-delimited checklist labels, or an empty string when confidence
    is too low to assign any type.
    """
    text = f"{title} {summary}".strip()
    if not text and not metadata_html:
        return ""

    blob = text.lower()
    signals = parse_data_type_signals(metadata_html)
    types: list[str] = []

    if _ARCHIVAL_DOCUMENTS_PATTERN.search(text) and "data publication" not in blob[:80]:
        # Scanned historical document packages — insufficient confidence.
        if not _text_matches_any(blob, _OBSERVATIONAL_TEXT_PATTERNS + _GIS_TEXT_PATTERNS):
            return ""

    if _text_matches_any(blob, _SURVEY_TEXT_PATTERNS) and re.search(
        r"\bvisitor\b|\brespondents?\b|\bquestionnaire\b|\bdemographics\b|\bn\s*=\s*\d+",
        blob,
        re.IGNORECASE,
    ):
        types.append(DATA_TYPE_SURVEY)

    if _text_matches_any(blob, _PROGRAM_SOURCE_TEXT_PATTERNS) or _signals_indicate_program_source(
        signals
    ):
        types.append(DATA_TYPE_PROGRAM_SOURCE)

    if _text_matches_any(blob, _GIS_TEXT_PATTERNS) or _signals_indicate_gis(signals, blob):
        types.append(DATA_TYPE_GIS)

    aggregate_match = _text_matches_any(blob, _AGGREGATE_TEXT_PATTERNS)
    if aggregate_match and not _RAW_OR_PLOT_DATA_PATTERN.search(text):
        types.append(DATA_TYPE_AGGREGATE)

    if _text_matches_any(blob, _ADMINISTRATIVE_TEXT_PATTERNS):
        types.append(DATA_TYPE_ADMINISTRATIVE)

    if _text_matches_any(blob, _EXPERIMENTAL_TEXT_PATTERNS):
        types.append(DATA_TYPE_EXPERIMENTAL)

    observational_match = _text_matches_any(blob, _OBSERVATIONAL_TEXT_PATTERNS)
    if (
        observational_match
        and not aggregate_match
        and DATA_TYPE_SURVEY not in types
        and not (DATA_TYPE_GIS in types and _gis_primary_product(blob))
    ):
        types.append(DATA_TYPE_OBSERVATIONAL)

    # Preserve stable ordering and drop duplicates.
    seen: set[str] = set()
    ordered: list[str] = []
    for data_type in types:
        if data_type not in seen:
            seen.add(data_type)
            ordered.append(data_type)

    return "; ".join(ordered)


def merge_usfs_metadata(detail: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    """Merge detail-page and FGDC metadata, preferring richer values."""
    merged = {**detail}
    for key, value in metadata.items():
        if key == "data_types":
            continue
        if value is None or value == "":
            continue
        if key not in merged or not merged.get(key):
            merged[key] = value
        elif key in ("time_start", "time_end"):
            merged[key] = value
    return merged
