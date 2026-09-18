"""
IRMA reference helpers: URLs, nested profile lists, and public Digital Files.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

PROFILE_PATH_MARKER = "profile"
IRMA_HOST = "irma.nps.gov"
PROFILE_URL_PREFIX = "https://irma.nps.gov/DataStore/Reference/Profile/"
DIGITAL_FILE_TYPE = "Digital File"


def reference_profile_url(reference_id: int) -> str:
    """
    Build the public IRMA Profile URL for a reference id.

    Args:
        reference_id: IRMA reference id.
    """
    return f"{PROFILE_URL_PREFIX}{int(reference_id)}"


def irma_project_id_from_source_url(source_url: str) -> int | None:
    """
    Extract an IRMA reference id from a Profile URL.

    Args:
        source_url: Candidate or stored source URL.
    """
    parsed = urlparse(source_url.strip())
    if parsed.netloc.lower() != IRMA_HOST:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[-2].lower() != PROFILE_PATH_MARKER:
        return None
    try:
        return int(parts[-1])
    except ValueError:
        return None


def is_public_token(value: Any) -> bool:
    """Return True when an IRMA visibility/fileAccess token is Public."""
    return str(value or "").strip().lower() == "public"


def as_reference_dicts(raw: Any) -> list[dict[str, Any]]:
    """
    Flatten IRMA nested list/object payloads into reference dicts.

    Args:
        raw: A list, or an object wrapping lists (e.g. ``{project: [...]}``).
    """
    items: list[Any]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = []
        for value in raw.values():
            if isinstance(value, list):
                items.extend(value)
    else:
        items = []
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        nested = item.get("reference")
        row = nested if isinstance(nested, dict) else item
        if isinstance(row, dict):
            rows.append(row)
    return rows


def profile_children(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return Program children, preferring ``children`` then ``projects``."""
    children = as_reference_dicts(profile.get("children"))
    if children:
        return children
    return as_reference_dicts(profile.get("projects"))


def profile_products(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Return Product summaries nested on a Project profile."""
    return as_reference_dicts(profile.get("products"))


def reference_id_of(row: dict[str, Any]) -> int | None:
    """Return referenceId/Id from a profile or collection row."""
    for key in ("referenceId", "Id", "id"):
        value = row.get(key)
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def is_public_digital_file(item: dict[str, Any]) -> bool:
    """Return True for an anonymously downloadable Digital File link."""
    if str(item.get("resourceType") or "") != DIGITAL_FILE_TYPE:
        return False
    if not str(item.get("url") or "").strip():
        return False
    if item.get("isPublic") is False:
        return False
    return True


def project_direct_public_file_count(profile: dict[str, Any]) -> int:
    """Count public Digital Files attached to the Project record itself."""
    if not is_public_token(profile.get("visibility")):
        return 0
    files = profile.get("filesAndLinks") or []
    if not isinstance(files, list):
        return 0
    return sum(1 for item in files if isinstance(item, dict) and is_public_digital_file(item))


def is_public_downloadable_product(product: dict[str, Any]) -> bool:
    """Return True when a Product lists public Digital Files for anonymous download."""
    return (
        int(product.get("fileCount") or 0) > 0
        and is_public_token(product.get("fileAccess"))
        and is_public_token(product.get("visibility"))
    )


def product_public_file_count(product: dict[str, Any]) -> int:
    """Return public file count for a Product summary, or 0 when restricted."""
    if not is_public_downloadable_product(product):
        return 0
    return int(product.get("fileCount") or 0)
