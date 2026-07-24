"""
Normalize project titles for inventory storage and sheet updates.
"""

from __future__ import annotations

import re

_CATALOG_TITLE_SUFFIX_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\s*\|\s*Agency for Healthcare Research and Quality\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"\s*\|\s*Medicaid\s*$", re.IGNORECASE),
)


def normalize_inventory_title(title: str | None) -> str:
    """
    Strip known catalog page title suffixes before storing or writing to the sheet.

    Data.gov catalog pages often append agency names to the HTML ``<title>`` (for
    example `` | Agency for Healthcare Research and Quality`` or `` | Medicaid``);
    the inventory **Title** column should contain only the dataset name.

    Args:
        title: Raw title from page metadata or storage.

    Returns:
        Title with known suffixes removed, or empty string when input is blank.
    """
    text = (title or "").strip()
    if not text:
        return ""
    for pattern in _CATALOG_TITLE_SUFFIX_PATTERNS:
        text = pattern.sub("", text).strip()
    return text
