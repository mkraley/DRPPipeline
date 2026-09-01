"""
Helpers for Baserow batch import spreadsheet column values.
"""

from __future__ import annotations

from urllib.parse import urlparse

from utils.file_utils import parse_file_size_to_bytes


def website_from_source_url(source_url: str) -> str:
    """
    Derive the Baserow ``Websites`` value from a dataset source URL.

    Returns the hostname with a leading ``www.`` removed (for example
    ``fs.usda.gov`` from ``https://www.fs.usda.gov/...``).

    Args:
        source_url: Original dataset URL.

    Returns:
        Hostname string, or empty when the URL has no host.
    """
    host = (urlparse((source_url or "").strip()).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def format_baserow_backup_title(title: str) -> str:
    """
    Format a dataset title for the Baserow Backups ``Dataset`` column.

    Titles containing a comma or forward slash are wrapped in double quotes so
    batch import matches the Datasets table name.

    Args:
        title: Normalized dataset title.

    Returns:
        Title safe for the Backups import column.
    """
    text = (title or "").strip()
    if not text:
        return ""
    if "," in text or "/" in text:
        return f'"{text}"'
    return text


def format_baserow_file_extensions(extensions: str) -> str:
    """
    Normalize extension list for Baserow ``File type`` (comma-separated, no spaces).

    Args:
        extensions: Comma- or space-separated extensions from storage.

    Returns:
        Lowercase extensions joined by commas without spaces.
    """
    raw = (extensions or "").replace(",", " ")
    tokens: list[str] = []
    for part in raw.split():
        token = part.strip().lstrip(".").lower()
        if token and token not in tokens:
            tokens.append(token)
    return ",".join(tokens)


def format_dataset_size_gb_jedec(size_value: str | int | float | None) -> str:
    """
    Convert a byte count or parseable size string to floating-point GB (binary/JEDEC).

    Args:
        size_value: Raw byte count or human-readable size from storage.

    Returns:
        Size in GB as a decimal string with a fractional part (e.g. ``1.0``),
        or empty when input is missing or invalid.
    """
    if size_value is None:
        return ""
    if isinstance(size_value, (int, float)):
        size_bytes = int(size_value)
    else:
        parsed = parse_file_size_to_bytes(str(size_value).strip())
        if parsed is None:
            return ""
        size_bytes = parsed
    if size_bytes < 0:
        size_bytes = 0
    gb = size_bytes / (1024**3)
    text = f"{gb:.6f}".rstrip("0").rstrip(".")
    if not text:
        return "0.0"
    if "." not in text:
        return f"{text}.0"
    return text


def baserow_contact_value(
    *,
    baserow_contact: str | None = None,
    google_username: str | None = None,
) -> str:
    """
    Return the Contact column value for Baserow batch import sheets.

    Args:
        baserow_contact: Configured contact email or name.
        google_username: Fallback when ``baserow_contact`` is empty.

    Returns:
        Trimmed contact string.
    """
    contact = (baserow_contact or "").strip()
    if contact:
        return contact
    return (google_username or "").strip()


def baserow_organization(agency: str, office: str) -> str:
    """
    Return the Baserow Organization value (office, or agency when office is blank).

    Args:
        agency: Agency name from project metadata.
        office: Office / organization name from project metadata.

    Returns:
        Organization string for the sheet.
    """
    org = (office or "").strip()
    if org:
        return org
    return (agency or "").strip()
