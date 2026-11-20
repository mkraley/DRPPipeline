"""Text and filename helpers for the AirData download page."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from sourcing.AqsFile import AqsFile
from sourcing.AqsSeries import AqsSeries
from utils.Logger import Logger

_SIZE_KB = re.compile(r"([\d,]+)\s*KB", re.IGNORECASE)
_ROWS = re.compile(r"([\d,]+)\s*Rows", re.IGNORECASE)
_YEAR_SUFFIX = re.compile(r"_(?:19|20)\d{2}\.zip$", re.IGNORECASE)


def series_from_bucket(
    section: str,
    column: str,
    bucket: dict[str, object],
) -> AqsSeries | None:
    """
    Create a series when the column has a stable file prefix.

    Args:
        section: Download-page heading.
        column: Column heading.
        bucket: Accumulated files, advisories, prefixes, and omitted count.

    Returns:
        The series, or None when the column has no usable files.
    """
    prefixes = [str(prefix) for prefix in typed_list(bucket, "prefixes")]
    series_id = _series_id(section, column, prefixes)
    if not series_id:
        return None
    files = file_list(bucket, "files") + file_list(bucket, "advisories")
    if not files and int(bucket["omitted"]) == 0:
        return None
    return AqsSeries(series_id, section, column, files, int(bucket["omitted"]))


def remember_prefix(bucket: dict[str, object], filename: str) -> None:
    """
    Keep the yearly filename prefix so a column of empty files still has an id.

    Args:
        bucket: Column accumulator.
        filename: Zip filename from the page.
    """
    match = _YEAR_SUFFIX.search(filename)
    if match is None:
        return
    prefix = filename[: match.start()]
    prefixes = typed_list(bucket, "prefixes")
    if prefix not in prefixes:
        prefixes.append(prefix)


def file_list(bucket: dict[str, object], key: str) -> list[AqsFile]:
    """
    Return a file list stored on a column bucket.

    Args:
        bucket: Column accumulator.
        key: ``files`` or ``advisories``.

    Returns:
        The list stored at ``key``.
    """
    return typed_list(bucket, key)


def typed_list(bucket: dict[str, object], key: str) -> list:
    """
    Return a list value from a bucket.

    Args:
        bucket: Column accumulator.
        key: List field name.

    Returns:
        The list stored at ``key``.

    Raises:
        TypeError: When the stored value is not a list.
    """
    value = bucket[key]
    if not isinstance(value, list):
        raise TypeError(f"Column bucket {key} is not a list")
    return value


def is_explicit_zero(text: str) -> bool:
    """
    Return True when the cell text gives a size of 0 KB.

    Args:
        text: Table cell text.
    """
    match = _SIZE_KB.search(text)
    return match is not None and _number(match.group(1)) == 0


def size_kb(text: str) -> int:
    """
    Return the KB size in cell text, or 0 when it is absent.

    Args:
        text: Table cell text.
    """
    match = _SIZE_KB.search(text)
    if match is None:
        return 0
    return _number(match.group(1))


def row_count(text: str) -> int:
    """
    Return the row count in cell text, or 0 when it is absent.

    Args:
        text: Table cell text.
    """
    match = _ROWS.search(text)
    if match is None:
        return 0
    return _number(match.group(1))


def zip_name(href: str) -> str:
    """
    Return the zip filename for an href, or an empty string.

    Args:
        href: Link href from the page.
    """
    return _named(href, ".zip")


def pdf_name(href: str) -> str:
    """
    Return the PDF filename for an href, or an empty string.

    Args:
        href: Link href from the page.
    """
    return _named(href, ".pdf")


def attr(attrs: list[tuple[str, str | None]], name: str) -> str:
    """
    Return an attribute value, or an empty string.

    Args:
        attrs: Tag attributes.
        name: Attribute name.
    """
    for key, value in attrs:
        if key == name and value:
            return value
    return ""


def _series_id(section: str, column: str, prefixes: list[str]) -> str:
    """Return the series id, or an empty string when the prefix is ambiguous."""
    if section.lower().startswith("site"):
        return "sites"
    if len(prefixes) == 1:
        return prefixes[0]
    Logger.warning(
        "AQS column %s / %s has file prefixes %s and was skipped",
        section,
        column,
        prefixes,
    )
    return ""


def _number(raw: str) -> int:
    """Parse a comma-separated integer."""
    return int(raw.replace(",", ""))


def _named(href: str, suffix: str) -> str:
    """Return the final path segment when it has ``suffix``."""
    name = urlparse(href).path.rsplit("/", 1)[-1]
    if name.lower().endswith(suffix):
        return name
    return ""
