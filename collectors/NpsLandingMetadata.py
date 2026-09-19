"""
Write IRMA landing-page metadata JSON next to collected project and product files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sourcing.NpsProfileGeography import (
    profile_bounding_box,
    profile_geographic_coverage,
    profile_units,
)
from sourcing.NpsProfileMetadata import (
    bibliography,
    contact_records,
    irma_date,
    profile_abstract,
    profile_dois,
    profile_keywords,
    profile_notes,
    profile_publisher,
    profile_purpose,
    profile_summary_html,
    profile_temporal_fields,
    profile_title,
)
from sourcing.NpsReferenceRules import (
    public_digital_files,
    reference_id_of,
    reference_profile_url,
)

PROJECT_METADATA_NAME = "project_metadata.json"
PRODUCT_METADATA_NAME = "product_metadata.json"


def landing_metadata_dict(profile: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON-serializable dict from an IRMA Profile landing page."""
    bib = bibliography(profile)
    reference_id = reference_id_of(profile)
    times = profile_temporal_fields(profile)
    payload: dict[str, Any] = {
        "reference_id": reference_id,
        "reference_type": str(profile.get("referenceType") or ""),
        "title": profile_title(profile),
        "url": reference_profile_url(reference_id) if reference_id is not None else "",
        "citation": str(profile.get("citation") or "").strip(),
        "abstract": profile_abstract(profile),
        "publisher": profile_publisher(profile),
        "contacts": contact_records(profile),
        "notes": profile_notes(profile),
        "purpose": profile_purpose(profile),
        "issued": irma_date(bib.get("issued")),
        "content_begin": irma_date(bib.get("contentBegin")),
        "content_end": irma_date(bib.get("contentEnd")),
        "units": profile_units(profile),
        "bounding_box": profile_bounding_box(profile),
        "geographic_coverage": profile_geographic_coverage(profile),
        "keywords": profile_keywords(profile),
        "summary": profile_summary_html(profile),
        "doi": "; ".join(profile_dois(profile)),
        "visibility": str(profile.get("visibility") or ""),
        "file_access": str(profile.get("fileAccess") or ""),
        "files": _file_entries(profile),
    }
    payload.update(times)
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}


def write_landing_metadata(dest: Path, profile: dict[str, Any]) -> None:
    """Write one landing-page metadata JSON file as UTF-8."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(landing_metadata_dict(profile), indent=2, ensure_ascii=False)
    dest.write_text(text + "\n", encoding="utf-8")


def _file_entries(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """List public Digital Files from the landing page."""
    entries: list[dict[str, Any]] = []
    for item in public_digital_files(profile):
        entry = {
            "file_name": str(item.get("fileName") or item.get("FileName") or ""),
            "url": str(item.get("url") or ""),
            "file_id": item.get("fileId") or item.get("resourceId"),
        }
        entries.append({key: value for key, value in entry.items() if value not in (None, "")})
    return entries
