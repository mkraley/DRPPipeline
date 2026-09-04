"""
Helpers for Baserow batch import spreadsheet column values.
"""

from __future__ import annotations

from urllib.parse import urlparse

from utils.file_utils import parse_file_size_to_bytes
from utils.title_utils import normalize_inventory_title

BASEROW_TITLE_MAX_LENGTH = 255
_URL_COLON_PLACEHOLDER = "\x00URLCOLON\x00"


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


def replace_colons_in_baserow_title(title: str) -> str:
    """
    Replace colons in a Baserow dataset title with em dashes or hyphens.

    Subtitle separators (``: ``) become an em dash. Remaining colons become
    `` - ``, except URL schemes (``://``) which are left unchanged.

    Args:
        title: Title after catalog-suffix normalization.

    Returns:
        Title with colons replaced.
    """
    text = (title or "").strip()
    if not text or ":" not in text:
        return text
    text = text.replace("://", _URL_COLON_PLACEHOLDER)
    text = text.replace(": ", " — ")
    text = text.replace(":", " - ")
    text = text.replace(_URL_COLON_PLACEHOLDER, "://")
    return " ".join(text.split())


def _truncate_baserow_title(text: str, max_len: int) -> str:
    """Truncate ``text`` at a word or punctuation boundary when longer than ``max_len``."""
    if len(text) <= max_len:
        return text
    window = text[:max_len]
    min_keep = int(max_len * 0.6)
    for sep in (" — ", " – ", " - ", ", ", "; ", " "):
        idx = window.rfind(sep)
        if idx >= min_keep:
            return window[:idx].rstrip(" ,;:-—–")
    return window.rstrip()


def format_baserow_dataset_title(title: str) -> tuple[str, str]:
    """
    Prepare a title for the Baserow ``Title for Datasets table`` column.

    Applies catalog-suffix stripping, colon replacement, and a 255-character
    limit. When truncated, the second return value is a note containing the
    full original title for the ``Notes`` column.

    Args:
        title: Raw title from storage or the inventory sheet.

    Returns:
        ``(formatted_title, truncation_note)``. The note is empty when the
        formatted title was not truncated.
    """
    original = normalize_inventory_title(title)
    if not original:
        return "", ""
    formatted = replace_colons_in_baserow_title(original)
    if len(formatted) <= BASEROW_TITLE_MAX_LENGTH:
        return formatted, ""
    truncated = _truncate_baserow_title(formatted, BASEROW_TITLE_MAX_LENGTH)
    note = (
        f"Full original title (truncated to {BASEROW_TITLE_MAX_LENGTH} "
        f"characters): {original}"
    )
    return truncated, note


def format_baserow_backup_title(title: str) -> str:
    """
    Format a dataset title for the Baserow Backups ``Dataset`` column.

    Copies the Datasets title. Titles containing a comma or forward slash are
    wrapped in double quotes so batch import matches the Datasets table name.

    Args:
        title: Formatted Datasets-table title (not yet quoted).

    Returns:
        Title safe for the Backups import column.
    """
    text = (title or "").strip()
    if not text:
        return ""
    if text.startswith('"') and text.endswith('"'):
        return text
    if "," in text or "/" in text:
        return f'"{text}"'
    return text


def format_baserow_file_extensions(extensions: str) -> str:
    """
    Normalize extension list for Baserow ``File type`` (comma-separated, no spaces).

    Args:
        extensions: Comma- or space-separated extensions from storage.

    Returns:
        Uppercase extensions joined by commas without spaces.
    """
    raw = (extensions or "").replace(",", " ")
    tokens: list[str] = []
    for part in raw.split():
        token = part.strip().lstrip(".").upper()
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
