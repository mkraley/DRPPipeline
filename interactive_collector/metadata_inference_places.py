"""Place names used when a downloaded table has a state column."""

from __future__ import annotations

import re

_STATE_PAIRS: tuple[tuple[str, str], ...] = (
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
    ("DC", "District of Columbia"), ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"),
    ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
    ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"),
    ("MD", "Maryland"), ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"),
    ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"),
    ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"),
    ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"), ("OH", "Ohio"),
    ("OK", "Oklahoma"), ("OR", "Oregon"), ("PA", "Pennsylvania"), ("RI", "Rhode Island"),
    ("SC", "South Carolina"), ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"),
    ("UT", "Utah"), ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"),
    ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming"),
)
_BY_ABBR = {abbr: name for abbr, name in _STATE_PAIRS}
_BY_NAME = {name.lower(): name for _abbr, name in _STATE_PAIRS}
_US_TEXT = re.compile(r"\bunited states\b|\bu\.s\. commercial\b|\bin the u\.s\.\b", re.IGNORECASE)


def geography_from_text(text: str) -> str:
    """Return United States when the text states that coverage."""
    if _US_TEXT.search(text):
        return "United States"
    return ""


def is_state_header(header: str) -> bool:
    """True when a column header is a state field rather than a status field."""
    lowered = header.lower()
    if "status" in lowered:
        return False
    return bool(re.search(r"\bstates?\b", header, re.IGNORECASE))


def coverage_from_state_values(values: list[str]) -> str:
    """
    Return a geography string when the values are U.S. states.

    A single state is named. Two to eight states are listed. More than eight
    states become United States. Mixed or unrecognized values are ignored.
    """
    nonempty = [value.strip() for value in values if value.strip()]
    if not nonempty:
        return ""
    names: list[str] = []
    seen: set[str] = set()
    recognized = 0
    for value in nonempty:
        name = _state_name(value)
        if not name:
            continue
        recognized += 1
        if name not in seen:
            seen.add(name)
            names.append(name)
    if recognized / len(nonempty) < 0.8:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) <= 8:
        return "; ".join(names)
    return "United States"


def _state_name(value: str) -> str:
    """Return the full state name for an abbreviation or name, else empty."""
    token = value.strip()
    if token.upper() in _BY_ABBR:
        return _BY_ABBR[token.upper()]
    return _BY_NAME.get(token.lower(), "")
