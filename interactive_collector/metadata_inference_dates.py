"""Parse year, month, and date values found in table cells."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from interactive_collector.metadata_inference_text import month_number

_YEAR = re.compile(r"^((?:19|20)\d{2})(?:\.0)?$")
_ISO = re.compile(r"^((?:19|20)\d{2})-(\d{2})(?:-(\d{2}))?$")
_US_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/((?:19|20)\d{2})$")


def column_dates(header: str, values: list[str]) -> list[str]:
    """Parse a date or year column."""
    if re.search(r"\byear\b", header, re.IGNORECASE) and "date" not in header.lower():
        return [token for token in (year_token(value) for value in values) if token]
    return [token for token in (parse_date(value) for value in values) if token]


def parse_date(value: str) -> str:
    """Return YYYY-MM-DD or YYYY-MM, or an Excel serial date when the number is one."""
    text = value.strip()
    iso = _ISO.fullmatch(text)
    if iso:
        if iso.group(3):
            return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
        return f"{iso.group(1)}-{iso.group(2)}"
    us_date = _US_DATE.fullmatch(text)
    if not us_date:
        return excel_serial(text)
    month, day, year = int(us_date.group(1)), int(us_date.group(2)), us_date.group(3)
    if 1 <= month <= 12 and 1 <= day <= 31:
        return f"{year}-{month:02d}-{day:02d}"
    return ""


def excel_serial(value: str) -> str:
    """Convert an Excel date serial in the plausible range to YYYY-MM-DD."""
    try:
        serial = float(value)
    except ValueError:
        return ""
    if not 20000 <= serial <= 80000:
        return ""
    day = datetime(1899, 12, 30) + timedelta(days=serial)
    return day.date().isoformat()


def year_token(value: str) -> str:
    """Return a four-digit year, or empty."""
    match = _YEAR.fullmatch(value.strip())
    return match.group(1) if match else ""


_BOUND = re.compile(
    r"^((?:19|20)\d{2})(?:-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?)?$"
)


def align_coverage_dates(
    start: str,
    end: str,
    *,
    today: date | None = None,
) -> tuple[str, str]:
    """
    Return start and end as YYYY, or both as YYYY-MM-DD.

    A year-month value expands to the first day for a start and the last day
    for an end. An end later than ``today`` is clipped to that day, or to the
    current year when both bounds are years.
    """
    current = today or date.today()
    start_parts = _coverage_parts(start)
    end_parts = _coverage_parts(end)
    if start_parts is None and end_parts is None:
        return "", ""
    day_precision = _needs_day(start_parts, end_parts)
    start_text = _format_bound(start_parts, is_end=False, today=current, day_precision=day_precision)
    end_text = _format_bound(end_parts, is_end=True, today=current, day_precision=day_precision)
    if start_text and end_text and start_text > end_text:
        start_text = end_text
    return start_text, end_text


def _coverage_parts(value: str) -> tuple[int, int, int] | None:
    """Return year, month, and day. Month and day are 0 when absent."""
    match = _BOUND.fullmatch((value or "").strip())
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2) or 0)
    day = int(match.group(3) or 0)
    if day and month:
        try:
            date(year, month, day)
        except ValueError:
            return None
    return year, month, day


def _needs_day(
    start: tuple[int, int, int] | None,
    end: tuple[int, int, int] | None,
) -> bool:
    """True when either bound names a month or a day."""
    return any(parts is not None and (parts[1] or parts[2]) for parts in (start, end))


def _format_bound(
    parts: tuple[int, int, int] | None,
    *,
    is_end: bool,
    today: date,
    day_precision: bool,
) -> str:
    """Format one bound, clipping an end that is still in the future."""
    if parts is None:
        return ""
    year, month, day = parts
    if not day_precision:
        if is_end and year > today.year:
            return str(today.year)
        return str(year)
    resolved = _as_date(year, month, day, is_end=is_end)
    if is_end and resolved > today:
        resolved = today
    return resolved.isoformat()


def _as_date(year: int, month: int, day: int, *, is_end: bool) -> date:
    """Expand a partial date to a calendar day."""
    if month == 0:
        return date(year, 12, 31) if is_end else date(year, 1, 1)
    if day == 0:
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, last_day if is_end else 1)
    return date(year, month, day)


def month_token(value: str) -> str:
    """Return a two-digit month from a number or month name."""
    text = value.strip()
    if re.fullmatch(r"\d{1,2}(?:\.0)?", text):
        month = int(float(text))
        if 1 <= month <= 12:
            return f"{month:02d}"
        return ""
    return month_number(text)
