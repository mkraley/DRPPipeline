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

DATALUMOS_TITLE_MAX_LENGTH = 250


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


def truncate_title_for_datalumos(
    title: str, max_len: int = DATALUMOS_TITLE_MAX_LENGTH
) -> str:
    """
    Truncate a project title to DataLumos's length limit without breaking mid-word.

    Normalizes whitespace, then if still over ``max_len`` cuts at the last space in the
    allowed span (when that keeps most of the title). Otherwise hard-truncates.
    Appends an ellipsis when text was removed.

    Args:
        title: Raw or partially cleaned title.
        max_len: Maximum character length (DataLumos default 250).

    Returns:
        Truncated title string.
    """
    normalized = " ".join(normalize_inventory_title(title).split())
    if len(normalized) <= max_len:
        return normalized

    suffix = "…"
    if max_len <= len(suffix):
        return normalized[:max_len]

    cut_at = max_len - len(suffix)
    candidate = normalized[:cut_at]
    last_space = candidate.rfind(" ")
    min_word_break = int(cut_at * 0.6)
    if last_space >= min_word_break:
        candidate = candidate[:last_space]

    return candidate.rstrip(" ,;:-") + suffix


def prepare_datalumos_title(title: str) -> str:
    """
    Apply Baserow colon rules then DataLumos length truncation.

    Args:
        title: Project title from storage.

    Returns:
        Title safe to write into the DataLumos ``#title`` field.
    """
    from utils.baserow_sheet_utils import format_baserow_dataset_title

    formatted, _note = format_baserow_dataset_title(title)
    return truncate_title_for_datalumos(formatted)
