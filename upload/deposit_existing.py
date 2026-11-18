"""
Detect agency, investigator, and time-period values already stored on a project.

A later upload reads ``getAttributes`` and skips an add call when the same
entry is already there. ``addOrg``, ``addPerson``, and ``addDateRange`` append,
so posting them again creates a second copy.

DataLumos returns Fedora resource URIs for these fields (not display text).
Any organization URI means agency is already stored; the URI never contains
the agency name. The same applies to person and time-period URIs.
"""

from __future__ import annotations

import json
import re
from typing import Any

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_US_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_YEAR = re.compile(r"\b(\d{4})\b")
_YEAR_ONLY = re.compile(r"^\d{4}$")
_ORG_URI = re.compile(r"/organizations/[^/\s]+", re.IGNORECASE)
_PERSON_URI = re.compile(r"/(?:persons|people)/[^/\s]+", re.IGNORECASE)
_PERIOD_URI = re.compile(r"/timePeriod/[^/\s]+", re.IGNORECASE)


def organization_present(value: Any, name: str) -> bool:
    """Return True when an organization is already stored on ``value``."""
    if _uri_present(value, _ORG_URI):
        return True
    wanted = name.strip().casefold()
    if not wanted:
        return False
    return any(text.casefold() == wanted for text in _entry_texts(value))


def person_present(value: Any, first_name: str, last_name: str) -> bool:
    """Return True when this person is already stored on ``value``."""
    if _uri_present(value, _PERSON_URI):
        return True
    first = first_name.strip().casefold()
    last = last_name.strip().casefold()
    display = f"{first} {last}".strip()
    for texts in _entries(value):
        folded = [text.casefold() for text in texts]
        if display and display in folded:
            return True
        if first and last and first in folded and last in folded:
            return True
        if first and not last and first in folded:
            return True
        if last and not first and last in folded:
            return True
    return False


def time_period_present(value: Any, start: str, end: str) -> bool:
    """
    Return True when a time period is already stored on ``value``.

    Fedora ``timePeriod`` URIs count as present. Display strings still match
    by date, including year-only bounds against full dates.
    """
    if _uri_present(value, _PERIOD_URI):
        return True
    start_key = _canonical_date(start)
    end_key = _canonical_date(end)
    if not start_key:
        return False
    for texts in _entries(value):
        found = _dates_in_texts(texts)
        if _date_matches(start_key, found) and (
            not end_key or _date_matches(end_key, found)
        ):
            return True
    return False


def _uri_present(value: Any, pattern: re.Pattern[str]) -> bool:
    """Return True when any stored text matches a Fedora child-resource URI."""
    for text in _entry_texts(value):
        if pattern.search(text):
            return True
    return False


def _entries(value: Any) -> list[list[str]]:
    """Return each stored entry as its own list of text values."""
    value = _decode_json_value(value)
    if isinstance(value, list):
        return [_texts(item) for item in value if _texts(item)]
    texts = _texts(value)
    if texts:
        return [texts]
    return []


def _entry_texts(value: Any) -> list[str]:
    """Return every text stored on ``value``, across entries."""
    texts: list[str] = []
    for entry in _entries(value):
        texts.extend(entry)
    return texts


def _texts(value: Any) -> list[str]:
    """Return the non-empty strings inside one stored value."""
    found: list[str] = []
    _collect(value, found)
    return found


def _collect(value: Any, found: list[str]) -> None:
    """Append strings from ``value`` into ``found``."""
    value = _decode_json_value(value)
    if isinstance(value, str):
        for part in value.split("~~"):
            text = part.strip()
            if text:
                found.append(text)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect(item, found)
        return
    if isinstance(value, list):
        for item in value:
            _collect(item, found)
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        found.append(str(value))


def _decode_json_value(value: Any) -> Any:
    """Parse a JSON array/object string once; otherwise return ``value``."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def _dates_in_texts(texts: list[str]) -> set[str]:
    """Return canonical dates found in one stored period."""
    found: set[str] = set()
    for text in texts:
        found.update(_dates_in_text(text))
    return found


def _dates_in_text(text: str) -> set[str]:
    """Return canonical dates written in one string."""
    found = {f"{year}-{month}-{day}" for year, month, day in _ISO_DATE.findall(text)}
    found.update(
        f"{year}-{int(month):02d}-{int(day):02d}"
        for month, day, year in _US_DATE.findall(text)
    )
    if not found:
        found.update(_YEAR.findall(text))
    return found


def _canonical_date(value: str) -> str:
    """Return one date in ``YYYY-MM-DD`` or ``YYYY`` form."""
    text = value.strip()
    if not text:
        return ""
    found = _dates_in_text(text)
    if len(found) == 1:
        return next(iter(found))
    return text


def _date_matches(wanted: str, found: set[str]) -> bool:
    """Return True when ``wanted`` is the same bound as one date in ``found``."""
    if wanted in found:
        return True
    if _YEAR_ONLY.fullmatch(wanted):
        return any(item == wanted or item.startswith(f"{wanted}-") for item in found)
    year = wanted[:4]
    if _YEAR_ONLY.fullmatch(year) and year in found:
        return True
    return False
