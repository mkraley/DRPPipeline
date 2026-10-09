"""Metadata values taken from downloaded table columns."""

from __future__ import annotations

import re
from typing import Callable

from interactive_collector.metadata_inference_dates import column_dates, month_token, year_token
from interactive_collector.metadata_inference_places import (
    coverage_from_state_values,
    is_state_header,
)
from interactive_collector.metadata_inference_text import data_types_from_text
from interactive_collector.table_preview import TablePreview

_DATE_WORD = re.compile(r"\b(date|year|quarter|month)\b", re.IGNORECASE)
_IGNORE_DATE = re.compile(r"\b(update|updated|download)\b", re.IGNORECASE)
_KEYWORD_HEADER = re.compile(r"\b(keywords?|subjects?|topics?|tags?)\b", re.IGNORECASE)


def keep_value_column(header: str) -> bool:
    """True when a column can supply dates, states, or an explicit keyword list."""
    return is_date_header(header) or is_state_header(header) or is_keyword_header(header)


def is_date_header(header: str) -> bool:
    """True for date, year, quarter, or month columns that are not update stamps."""
    if _IGNORE_DATE.search(header):
        return False
    return bool(_DATE_WORD.search(header))


def is_keyword_header(header: str) -> bool:
    """True for an explicit keyword, subject, topic, or tag column."""
    return bool(_KEYWORD_HEADER.search(header))


def apply_preview(preview: TablePreview, fields: dict[str, str]) -> None:
    """Merge one table into ``fields`` without replacing stated United States coverage."""
    merge_data_type(fields, data_types_from_text(" ".join(preview.headers)))
    merge_keywords(fields, keywords_from_preview(preview))
    if preview.truncated:
        return
    start, end = dates_from_preview(preview)
    merge_dates(fields, start, end)
    if fields.get("geographic_coverage") == "United States":
        return
    coverage = coverage_from_preview(preview)
    if coverage:
        fields["geographic_coverage"] = coverage


def dates_from_preview(preview: TablePreview) -> tuple[str, str]:
    """Return the earliest and latest dates in date columns."""
    found = combined_year_months(preview)
    year_index, month_index = _year_month_indexes(preview)
    combined = year_index is not None and month_index is not None
    for index, header in enumerate(preview.headers):
        if not is_date_header(header):
            continue
        if combined and index in {year_index, month_index}:
            continue
        found.extend(column_dates(header, preview.columns.get(index, [])))
    present = [value for value in found if value]
    if not present:
        return "", ""
    return min(present), max(present)


def combined_year_months(preview: TablePreview) -> list[str]:
    """Pair separate Year and Month columns into YYYY-MM values."""
    year_index, month_index = _year_month_indexes(preview)
    if year_index is None or month_index is None:
        return []
    years = preview.columns.get(year_index, [])
    months = preview.columns.get(month_index, [])
    paired: list[str] = []
    for year, month in zip(years, months):
        year_text = year_token(year)
        month_text = month_token(month)
        if year_text and month_text:
            paired.append(f"{year_text}-{month_text}")
    return paired


def keywords_from_preview(preview: TablePreview) -> str:
    """Join keyword-column values with phrases taken from headers and categories."""
    from interactive_collector.metadata_inference_keywords import keywords_from_table

    values: list[str] = []
    for index, header in enumerate(preview.headers):
        if is_keyword_header(header):
            values.extend(preview.columns.get(index, []))
    values.extend(
        part.strip() for part in keywords_from_table(preview).split(";") if part.strip()
    )
    return join_terms(values)


def coverage_from_preview(preview: TablePreview) -> str:
    """Return geography from state columns."""
    values: list[str] = []
    for index, header in enumerate(preview.headers):
        if is_state_header(header):
            values.extend(preview.columns.get(index, []))
    return coverage_from_state_values(values)


def join_terms(values: list[str]) -> str:
    """Deduplicate short terms."""
    kept: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip()
        key = text.lower()
        if not text or len(text) > 60 or key in seen:
            continue
        seen.add(key)
        kept.append(text)
        if len(kept) == 15:
            break
    return "; ".join(kept)


def merge_keywords(fields: dict[str, str], extra: str) -> None:
    """Append keyword terms that are not already present."""
    if not extra:
        return
    current = [part.strip() for part in fields.get("keywords", "").split(";") if part.strip()]
    incoming = [part.strip() for part in extra.split(";")]
    fields["keywords"] = join_terms(current + incoming)


def merge_dates(fields: dict[str, str], start: str, end: str) -> None:
    """Widen the date range with dates found in a file."""
    if start:
        fields["time_start"] = min(fields.get("time_start") or start, start)
    if end:
        fields["time_end"] = max(fields.get("time_end") or end, end)


def merge_data_type(fields: dict[str, str], extra: str) -> None:
    """Add data-type labels that are not already present."""
    if not extra:
        return
    current = [part.strip() for part in fields.get("data_types", "").split(";") if part.strip()]
    for label in extra.split(";"):
        text = label.strip()
        if text and text not in current:
            current.append(text)
    fields["data_types"] = "; ".join(current)


def _year_month_indexes(preview: TablePreview) -> tuple[int | None, int | None]:
    """Return indexes of Year and Month headers."""
    return _header_index(preview, _is_year_header), _header_index(preview, _is_month_header)


def _is_year_header(header: str) -> bool:
    """True for a Year column that is not also a month column."""
    return bool(re.search(r"\byear\b", header, re.IGNORECASE)) and "month" not in header.lower()


def _is_month_header(header: str) -> bool:
    """True for a Month column that is not also a year column."""
    return bool(re.search(r"\bmonth\b", header, re.IGNORECASE)) and "year" not in header.lower()


def _header_index(preview: TablePreview, predicate: Callable[[str], bool]) -> int | None:
    """Return the first header index matching ``predicate``."""
    for index, header in enumerate(preview.headers):
        if predicate(header):
            return index
    return None
