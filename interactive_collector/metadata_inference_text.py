"""Read dates, data types, and keyword lists that are written in the source text."""

from __future__ import annotations

import re

from collectors.UsfsMetadataExtractor import (
    DATA_TYPE_ADMINISTRATIVE,
    DATA_TYPE_GIS,
    DATA_TYPE_OBSERVATIONAL,
    DATA_TYPE_SURVEY,
)

_MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}
_QUARTER_MONTH = {"1": "01", "2": "04", "3": "07", "4": "10"}
_MONTH_PATTERN = "|".join(_MONTHS)
_SINCE_QUARTER = re.compile(rf"\bsince\s+Q([1-4])\s+((?:19|20)\d{{2}})\b", re.IGNORECASE)
_SINCE_MONTH = re.compile(
    rf"\bsince\s+({_MONTH_PATTERN})\s+((?:19|20)\d{{2}})\b",
    re.IGNORECASE,
)
_SINCE_YEAR = re.compile(r"\bsince\s+((?:19|20)\d{2})\b", re.IGNORECASE)
_YEAR_RANGE = re.compile(r"\b((?:19|20)\d{2})\s*[\u2013\-]\s*((?:19|20)\d{2})\b")
_BEFORE_MONTH = re.compile(
    rf"\bbefore\s+({_MONTH_PATTERN})\s+((?:19|20)\d{{2}})\b",
    re.IGNORECASE,
)
_LAST_UPDATED = re.compile(
    r"last updated\s*:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
    re.IGNORECASE,
)
_ADMIN = re.compile(
    r"\b(dockets?|licensees?|licenses?|licences?|enforcement|inspections?|violations?|permits?)\b",
    re.IGNORECASE,
)
_OBSERVATIONAL = re.compile(
    r"\braw data\b|\bindicators?\b|\bnumerical value\b|\bdaily\b.{0,40}\bstatus\b",
    re.IGNORECASE,
)
_SURVEY = re.compile(r"\bquestionnaire\b|\brespondents?\b", re.IGNORECASE)
_GIS = re.compile(
    r"\bshapefiles?\b|\bgeospatial\b|\bgeographic information system\b",
    re.IGNORECASE,
)
_KEYWORDS_LINE = re.compile(r"\bkeywords?\s*:\s*([^.]{1,240})", re.IGNORECASE)
_TYPE_ORDER = (
    DATA_TYPE_ADMINISTRATIVE,
    DATA_TYPE_OBSERVATIONAL,
    DATA_TYPE_SURVEY,
    DATA_TYPE_GIS,
)


def plain_text(value: str) -> str:
    """Strip tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", text).strip()


def dates_from_text(text: str) -> tuple[str, str]:
    """
    Return start and end dates stated in prose.

    Rolling phrases such as "past month" are not converted into dates.
    A "last updated" stamp is ignored.
    """
    cleaned = _LAST_UPDATED.sub(" ", text)
    starts = [_quarter_start(match) for match in _SINCE_QUARTER.finditer(cleaned)]
    starts.extend(_month_start(match) for match in _SINCE_MONTH.finditer(cleaned))
    starts.extend(match.group(1) for match in _SINCE_YEAR.finditer(cleaned))
    ends: list[str] = []
    for match in _YEAR_RANGE.finditer(cleaned):
        starts.append(match.group(1))
        ends.append(match.group(2))
    ends.extend(_month_end(match) for match in _BEFORE_MONTH.finditer(cleaned))
    return _earliest(starts), _latest(ends)


def data_types_from_text(text: str) -> str:
    """Return DataLumos data-type labels supported by the text."""
    found: list[str] = []
    if _ADMIN.search(text):
        found.append(DATA_TYPE_ADMINISTRATIVE)
    if _OBSERVATIONAL.search(text):
        found.append(DATA_TYPE_OBSERVATIONAL)
    if _SURVEY.search(text):
        found.append(DATA_TYPE_SURVEY)
    if _GIS.search(text):
        found.append(DATA_TYPE_GIS)
    return "; ".join(label for label in _TYPE_ORDER if label in found)


def keywords_from_text(text: str) -> str:
    """Return a keyword list only when the text has a Keywords label."""
    match = _KEYWORDS_LINE.search(text)
    if not match:
        return ""
    parts = re.split(r"\s*;\s*|\s*,\s*", match.group(1).strip())
    kept = [part.strip() for part in parts if part.strip() and len(part.strip()) <= 60]
    if len(kept) < 2:
        return ""
    return "; ".join(kept[:15])


def month_number(name: str) -> str:
    """Return a zero-padded month for an English month name, or empty."""
    return _MONTHS.get(name.strip().lower(), "")


def _quarter_start(match: re.Match[str]) -> str:
    """Return the first day of a 'since Qn YYYY' match."""
    quarter, year = match.group(1), match.group(2)
    return f"{year}-{_QUARTER_MONTH[quarter]}-01"


def _month_start(match: re.Match[str]) -> str:
    """Return YYYY-MM for a 'since Month YYYY' match."""
    month = _MONTHS[match.group(1).lower()]
    return f"{match.group(2)}-{month}"


def _month_end(match: re.Match[str]) -> str:
    """Return YYYY-MM for a 'before Month YYYY' match."""
    month = _MONTHS[match.group(1).lower()]
    return f"{match.group(2)}-{month}"


def _earliest(values: list[str]) -> str:
    """Return the earliest non-empty date string."""
    present = [value for value in values if value]
    return min(present) if present else ""


def _latest(values: list[str]) -> str:
    """Return the latest non-empty date string."""
    present = [value for value in values if value]
    return max(present) if present else ""
