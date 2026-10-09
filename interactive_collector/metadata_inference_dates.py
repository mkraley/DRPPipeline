"""Parse year, month, and date values found in table cells."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

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


def month_token(value: str) -> str:
    """Return a two-digit month from a number or month name."""
    text = value.strip()
    if re.fullmatch(r"\d{1,2}(?:\.0)?", text):
        month = int(float(text))
        if 1 <= month <= 12:
            return f"{month:02d}"
        return ""
    return month_number(text)
