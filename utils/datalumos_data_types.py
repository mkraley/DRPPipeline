"""
DataLumos kindOfData controlled vocabulary and alias normalization.

Upload automation requires exact checklist labels. Collectors may store
short aliases (for example ``GIS``); normalize before filling the form.
"""

from __future__ import annotations

import re

DATA_TYPE_ADMINISTRATIVE = "Administrative records data"
DATA_TYPE_AGGREGATE = "Aggregate data"
DATA_TYPE_EXPERIMENTAL = "Experimental data"
DATA_TYPE_GIS = "Geographic information system (GIS) data"
DATA_TYPE_OBSERVATIONAL = "Observational data"
DATA_TYPE_PROGRAM_SOURCE = "Program source code"
DATA_TYPE_SURVEY = "Survey data"

ALL_DATA_TYPES: frozenset[str] = frozenset(
    {
        DATA_TYPE_ADMINISTRATIVE,
        DATA_TYPE_AGGREGATE,
        DATA_TYPE_EXPERIMENTAL,
        DATA_TYPE_GIS,
        DATA_TYPE_OBSERVATIONAL,
        DATA_TYPE_PROGRAM_SOURCE,
        DATA_TYPE_SURVEY,
    }
)

_DATA_TYPE_ALIASES: dict[str, str] = {
    "gis": DATA_TYPE_GIS,
    "geospatial": DATA_TYPE_GIS,
    "tabular": DATA_TYPE_OBSERVATIONAL,
    "observational": DATA_TYPE_OBSERVATIONAL,
    "survey": DATA_TYPE_SURVEY,
    "aggregate": DATA_TYPE_AGGREGATE,
    "administrative": DATA_TYPE_ADMINISTRATIVE,
    "experimental": DATA_TYPE_EXPERIMENTAL,
    "program source code": DATA_TYPE_PROGRAM_SOURCE,
    "other": "",
}

_CANONICAL_BY_LOWER = {label.lower(): label for label in ALL_DATA_TYPES}


def normalize_datalumos_data_types(data_type: str) -> list[str]:
    """
    Normalize semicolon-delimited data type text to DataLumos checklist labels.

    Args:
        data_type: Raw ``data_types`` field value from Storage.

    Returns:
        Deduplicated canonical labels in first-seen order. Unknown tokens are omitted.
    """
    if not data_type or not str(data_type).strip():
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"\s*;\s*", str(data_type)):
        token = part.strip()
        if not token:
            continue
        canonical = _canonical_label(token)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)
    return normalized


def _canonical_label(token: str) -> str:
    """Map one token to a canonical DataLumos label, if possible."""
    lowered = token.strip().lower()
    if lowered in _DATA_TYPE_ALIASES:
        return _DATA_TYPE_ALIASES[lowered]
    if lowered in _CANONICAL_BY_LOWER:
        return _CANONICAL_BY_LOWER[lowered]
    return ""
