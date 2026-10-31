"""
Build the metadata payload for a DataLumos deposit from a Storage row.

Production titles are prepared the same way as the workspace form. The trial
helper prefixes the title with ``TRIAL``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from upload.DataLumosUploader import _agency_values_for_upload
from utils.IcpsrGeographicNormalizer import parse_geographic_coverage_field
from utils.PrincipalInvestigators import deserialize_investigators
from utils.datalumos_data_types import normalize_datalumos_data_types
from utils.project_utils import get_field
from utils.summary_html import prepare_summary_for_datalumos_upload
from utils.temporal_utils import align_upload_time_period
from utils.title_utils import prepare_datalumos_title

_CDC_AGENCY = (
    "United States Department of Health and Human Services. "
    "Centers for Disease Control and Prevention"
)


@dataclass(frozen=True)
class DepositMetadata:
    """Metadata written after the project is created."""

    title: str
    agencies: tuple[str, ...]
    investigators: tuple[tuple[str, str, str], ...]
    summary: str
    original_url: str
    keywords: tuple[str, ...]
    geography: tuple[str, ...]
    time_start: str
    time_end: str
    data_types: tuple[str, ...]
    notes: str


def metadata_from_project(project: dict[str, Any]) -> DepositMetadata:
    """
    Prepare one Storage project for a production deposit.

    Args:
        project: Row from Storage. Read only; this function does not write it.

    Returns:
        Field values ready to post, with the normal DataLumos title.
    """
    return _from_project(project, prepare_datalumos_title(get_field(project, "title")))


def trial_metadata_from_project(project: dict[str, Any]) -> DepositMetadata:
    """
    Prepare one Storage project for a deposit-API trial.

    Args:
        project: Row from Storage. Read only; this function does not write it.

    Returns:
        Field values ready to post. The title already includes the ``TRIAL`` prefix.
    """
    raw_title = get_field(project, "title")
    titled = prepare_datalumos_title(f"TRIAL {raw_title}" if raw_title else "TRIAL")
    return _from_project(project, titled)


def _from_project(project: dict[str, Any], title: str) -> DepositMetadata:
    """Build metadata for a title that is already prepared."""
    start, end = align_upload_time_period(
        get_field(project, "time_start"),
        get_field(project, "time_end"),
    )
    return DepositMetadata(
        title=title,
        agencies=tuple(_agencies(project)),
        investigators=tuple(_investigators(get_field(project, "principal_investigators"))),
        summary=_html_or_blank(get_field(project, "summary")),
        original_url=get_field(project, "source_url"),
        keywords=tuple(_keywords(get_field(project, "keywords"))),
        geography=tuple(parse_geographic_coverage_field(get_field(project, "geographic_coverage"))),
        time_start=start,
        time_end=end,
        data_types=tuple(normalize_datalumos_data_types(get_field(project, "data_types"))),
        notes=_notes(get_field(project, "collection_notes"), get_field(project, "download_date")),
    )


def _agencies(project: dict[str, Any]) -> list[str]:
    """Return agency and office values, expanding the CDC short name."""
    values = _agency_values_for_upload(
        get_field(project, "agency"),
        get_field(project, "office"),
    )
    expanded: list[str] = []
    for value in values:
        expanded.append(_CDC_AGENCY if value == "CDC" else value)
    return expanded


def _investigators(raw: str) -> list[tuple[str, str, str]]:
    """Return ``(first, last, affiliation)`` rows for each named investigator."""
    people: list[tuple[str, str, str]] = []
    for person in deserialize_investigators(raw):
        first = (person.get("first_name") or "").strip()
        last = (person.get("last_name") or "").strip()
        affiliation = (person.get("affiliation") or "").strip()
        if first or last:
            people.append((first, last, affiliation))
    return people


def _keywords(raw: str) -> list[str]:
    """Split keywords the way the uploader does, dropping very short tokens."""
    cleaned = raw.replace("'", "").replace("[", "").replace("]", "").replace('"', "")
    parts = re.split(r"[,;]+", cleaned)
    terms: list[str] = []
    for part in parts:
        token = part.strip().strip("&").strip()
        if len(token.strip(" '")) > 2:
            terms.append(token)
    return terms


def _notes(notes: str, download_date: str) -> str:
    """Combine collection notes and the download date, then prepare HTML."""
    download_part = f"(Downloaded {download_date})" if download_date else ""
    text = notes.strip()
    if text and download_part:
        combined = f"{text} {download_part}"
    elif download_part:
        combined = download_part
    else:
        combined = ""
    return _html_or_blank(combined)


def _html_or_blank(value: str) -> str:
    """Prepare HTML for a wysihtml5 field, or return an empty string."""
    if not value.strip():
        return ""
    return prepare_summary_for_datalumos_upload(value).strip()
