"""
Parse Globus File Manager URLs from ADC status notes.

Example::

    https://app.globus.org/file-manager?origin_id=<UUID>&origin_path=%2Fnode29313%2F
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

_GLOBUS_HOST = "app.globus.org"
_URL_IN_TEXT = re.compile(r"https?://app\.globus\.org/file-manager[^\s\]\)\"\'<>]*", re.I)


@dataclass(frozen=True)
class GlobusFileManagerUrl:
    """Globus collection endpoint and path from a File Manager link."""

    origin_id: str
    origin_path: str

    @classmethod
    def from_status_notes(cls, status_notes: str | None) -> GlobusFileManagerUrl | None:
        """
        Extract Globus endpoint details from a status_notes field.

        Args:
            status_notes: Storage status_notes text (may include ``External data URL:``).

        Returns:
            Parsed URL or None when no Globus File Manager link is present.
        """
        if not status_notes:
            return None
        text = status_notes.strip()
        url = text
        if text.startswith("External data URL:"):
            url = text.split(":", 1)[1].strip()
        elif not text.startswith("http"):
            match = _URL_IN_TEXT.search(text)
            if not match:
                return None
            url = match.group(0)
        return cls.from_url(url)

    @classmethod
    def from_url(cls, url: str) -> GlobusFileManagerUrl | None:
        """
        Parse a Globus File Manager URL.

        Args:
            url: Full or partial File Manager URL.

        Returns:
            Parsed endpoint details, or None when required query params are missing.
        """
        parsed = urlparse(url.strip())
        if _GLOBUS_HOST not in parsed.netloc.lower():
            return None
        params = parse_qs(parsed.query)
        origin_ids = params.get("origin_id") or params.get("originID")
        origin_paths = params.get("origin_path") or params.get("originPath")
        if not origin_ids or not origin_paths:
            return None
        origin_id = origin_ids[0].strip()
        origin_path = unquote(origin_paths[0].strip())
        if not origin_path.startswith("/"):
            origin_path = f"/{origin_path}"
        if not origin_id:
            return None
        return cls(origin_id=origin_id, origin_path=origin_path)

    def is_globus_host(self) -> bool:
        """Return True (always for valid instances)."""
        return bool(self.origin_id and self.origin_path)
