"""
Temporal coverage helpers for Storage and DataLumos upload.

DataLumos requires both ``time_start`` and ``time_end`` or neither. These helpers
infer missing end dates from filenames and pair partial ranges.
"""

from __future__ import annotations

import re
from typing import Any

from collectors.UsfsMetadataExtractor import normalize_temporal_date

_ISO_DATE_RE = re.compile(
    r"(?<!\d)((19|20)\d{2})[-_/](0[1-9]|1[0-2])[-_/](0[1-9]|[12]\d|3[01])(?!\d)"
)
_COMPACT_DATE_RE = re.compile(
    r"(?<!\d)((19|20)\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)"
)
_YEAR_MONTH_RE = re.compile(r"(?<!\d)((19|20)\d{2})(0[1-9]|1[0-2])(?!\d)")
_YEAR_RE = re.compile(r"(?<!\d)((19|20)\d{2})(?!\d)")


def extract_dates_from_text(text: str) -> list[str]:
    """
    Extract normalized date strings embedded in free text (e.g. filenames).

    Args:
        text: Input string to scan for date-like tokens.

    Returns:
        Normalized dates in discovery order (may include duplicates).
    """
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()

    for match in _ISO_DATE_RE.finditer(text):
        raw = f"{match.group(1)}-{match.group(3)}-{match.group(4)}"
        _append_date(found, seen, raw)

    for match in _COMPACT_DATE_RE.finditer(text):
        raw = f"{match.group(1)}-{match.group(3)}-{match.group(4)}"
        _append_date(found, seen, raw)

    for match in _YEAR_MONTH_RE.finditer(text):
        raw = f"{match.group(1)}-{match.group(2)}"
        _append_date(found, seen, raw)

    for match in _YEAR_RE.finditer(text):
        _append_date(found, seen, match.group(1))

    return found


def infer_time_end_from_filenames(filenames: list[str]) -> str:
    """
    Infer the latest date appearing in a list of filenames.

    Args:
        filenames: Basenames or paths to scan for embedded dates.

    Returns:
        Normalized latest date, or empty string when none are found.
    """
    dates: list[str] = []
    for name in filenames:
        dates.extend(extract_dates_from_text(name))
    if not dates:
        return ""
    return max(dates, key=_date_sort_key)


def infer_time_end_from_article_files(article: dict[str, Any]) -> str:
    """
    Infer ``time_end`` from Figshare article file names.

    Args:
        article: Full Figshare article JSON.

    Returns:
        Normalized latest date from ``article['files']`` names.
    """
    filenames = [
        str(file_obj.get("name") or "")
        for file_obj in (article.get("files") or [])
        if file_obj.get("name")
    ]
    return infer_time_end_from_filenames(filenames)


def pair_time_fields(time_start: str | None, time_end: str | None) -> dict[str, str]:
    """
    Ensure DataLumos-compatible temporal fields: both set or neither.

    When only one bound is present, copy it to the missing bound.

    Args:
        time_start: Coverage start date or year.
        time_end: Coverage end date or year.

    Returns:
        Dict with ``time_start`` and/or ``time_end`` when at least one input is set.
    """
    start = (time_start or "").strip()
    end = (time_end or "").strip()
    if start and end:
        return {"time_start": start, "time_end": end}
    if start:
        return {"time_start": start, "time_end": start}
    if end:
        return {"time_start": end, "time_end": end}
    return {}


def apply_temporal_inference(
    time_start: str,
    time_end: str,
    *,
    filenames: list[str] | None = None,
) -> dict[str, str]:
    """
    Fill a missing end date from filenames, then pair partial ranges.

    Args:
        time_start: Explicit or inferred start date.
        time_end: Explicit end date (may be empty).
        filenames: Optional filenames to scan when ``time_end`` is missing.

    Returns:
        Paired ``time_start`` / ``time_end`` suitable for Storage.
    """
    start = (time_start or "").strip()
    end = (time_end or "").strip()

    if start and not end and filenames:
        inferred_end = infer_time_end_from_filenames(filenames)
        if inferred_end and _date_sort_key(inferred_end) >= _date_sort_key(start):
            end = inferred_end

    return pair_time_fields(start, end)


def merge_and_pair_time_updates(
    current: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, str]:
    """
    Merge proposed time field updates with current values and pair them.

    Args:
        current: Existing project record dict.
        updates: Incoming field updates that may include ``time_start`` / ``time_end``.

    Returns:
        Paired time fields to write (may be empty when both bounds are blank).
    """
    if "time_start" not in updates and "time_end" not in updates:
        return {}

    start = updates.get("time_start", current.get("time_start"))
    end = updates.get("time_end", current.get("time_end"))
    if start is None:
        start = ""
    if end is None:
        end = ""
    return pair_time_fields(str(start), str(end))


def _append_date(found: list[str], seen: set[str], raw: str) -> None:
    """Append a normalized date when it has not already been recorded."""
    normalized = normalize_temporal_date(raw)
    if normalized and normalized not in seen:
        seen.add(normalized)
        found.append(normalized)


def _date_sort_key(normalized: str) -> tuple[int, int, int]:
    """Return a sortable key for normalized temporal strings."""
    if re.fullmatch(r"\d{4}", normalized):
        return (int(normalized), 1, 1)
    parts = normalized.split("-")
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return (int(parts[0]), int(parts[1]), 1)
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    digits = re.sub(r"\D", "", normalized)
    if len(digits) >= 4:
        year = int(digits[:4])
        month = int(digits[4:6]) if len(digits) >= 6 else 1
        day = int(digits[6:8]) if len(digits) >= 8 else 1
        return (year, month, day)
    return (0, 0, 0)
