"""
Detect agency, investigator, and time-period values already stored on a project.

A later upload reads ``getAttributes`` and skips an add call when the same
entry is already there. ``addOrg``, ``addPerson``, and ``addDateRange`` append,
so posting them again creates a second copy.
"""

from __future__ import annotations

import re
from typing import Any

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_US_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_YEAR = re.compile(r"\b(\d{4})\b")


def organization_present(value: Any, name: str) -> bool:
    """Return True when ``name`` is already an organization on ``value``."""
    wanted = name.strip().casefold()
    if not wanted:
        return False
    return any(text.casefold() == wanted for text in _entry_texts(value))


def person_present(value: Any, first_name: str, last_name: str) -> bool:
    """Return True when this person is already stored on ``value``."""
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
    """Return True when this start and end are already one stored period."""
    start_key = _canonical_date(start)
    end_key = _canonical_date(end)
    if not start_key:
        return False
    for texts in _entries(value):
        found = _dates_in_texts(texts)
        if start_key in found and (not end_key or end_key in found):
            return True
    return False


def _entries(value: Any) -> list[list[str]]:
    """Return each stored entry as its own list of text values."""
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
    if isinstance(value, str):
        text = value.strip()
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
