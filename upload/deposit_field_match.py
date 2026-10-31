"""
Map deposit attributes onto the fields the uploader fills.
"""

from __future__ import annotations

import re
from typing import Any

from upload.DepositAttribute import DepositAttribute

_KEY_FALLBACK: dict[str, str] = {
    "summary": "dcterms_description",
    "original_url": "imeta_sourceURL",
    "notes": "imeta_collectionNotes",
    "data_types": "disco_kindOfData",
    "geography": "dcterms_location",
}

_EXACT_LABELS: dict[str, frozenset[str]] = {
    "summary": frozenset({"summary", "description", "project description"}),
    "original_url": frozenset({
        "original url",
        "source url",
        "alternative url",
        "distribution url",
    }),
    "keywords": frozenset({"subject terms"}),
    "geography": frozenset({"geographic coverage"}),
    "time_period": frozenset({"time period", "time period covered"}),
    "data_types": frozenset({"kind of data", "data type", "data types"}),
    "notes": frozenset({"collection notes", "notes"}),
    "agency": frozenset({"government agency", "organization/agency", "agency"}),
    "investigators": frozenset({
        "principal investigator",
        "principal investigators",
        "principal investigator(s)",
    }),
}


def match_fields(attrs: list[DepositAttribute]) -> dict[str, DepositAttribute]:
    """Map pipeline field names to attributes using keys, then labels."""
    matched: dict[str, DepositAttribute] = {}
    by_key = {attr.key: attr for attr in attrs}
    for field, key in _KEY_FALLBACK.items():
        attr = by_key.get(key)
        if attr is not None:
            matched[field] = attr
    for attr in attrs:
        field = _field_for_attr(attr)
        if field and field not in matched:
            matched[field] = attr
    return matched


def suggestion_texts(body: Any) -> list[str]:
    """Normalize a suggestSubjectTerms body into display strings."""
    if isinstance(body, list):
        return _texts_from_items(body)
    if isinstance(body, dict):
        for key in ("results", "items", "terms", "data"):
            items = body.get(key)
            if isinstance(items, list):
                return _texts_from_items(items)
    return []


def _field_for_attr(attr: DepositAttribute) -> str:
    """Return the pipeline field for an attribute, or an empty string."""
    label = _clean_label(attr.label)
    for field, labels in _EXACT_LABELS.items():
        if label in labels:
            return field
    control = attr.ui_control.casefold()
    if control == "keyword":
        return "keywords"
    if control in {"timeperiod", "collectiondate"}:
        return "time_period"
    if "agency" in label:
        return "agency"
    if label.startswith("principal investigator"):
        return "investigators"
    return ""


def _clean_label(label: str) -> str:
    """Lowercase a label and drop trailing punctuation."""
    cleaned = label.casefold().replace(":", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def _texts_from_items(items: list[Any]) -> list[str]:
    """Pull non-empty strings out of a suggestion list."""
    texts: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            texts.append(item)
            continue
        if isinstance(item, dict):
            text = _dict_text(item)
            if text:
                texts.append(text)
    return texts


def _dict_text(item: dict[str, Any]) -> str:
    """Return the first text-like value on a suggestion object."""
    for key in ("text", "label", "term", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""
