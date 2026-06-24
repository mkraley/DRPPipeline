"""
List dataset files from Zenodo via the public REST API.

Zenodo DOIs use the ``10.5281/zenodo.*`` prefix.
"""

from __future__ import annotations

import re
from typing import Any

import requests

ZENODO_API_BASE = "https://zenodo.org/api/records"
DEFAULT_HEADERS = {"User-Agent": "DRPPipeline/1.0", "Accept": "application/json"}
_ZENODO_RECORD_RE = re.compile(r"10\.5281/zenodo\.(\d+)", re.IGNORECASE)


class ZenodoApiClient:
    """Resolve Zenodo dataset DOIs to downloadable file metadata."""

    def list_files_for_doi(self, doi: str) -> list[dict[str, Any]]:
        """
        List files for a Zenodo record DOI.

        Args:
            doi: Full DOI, e.g. ``10.5281/zenodo.17627111``.

        Returns:
            Dicts with keys ``name``, ``url``, ``size_bytes``, and ``source``.
        """
        record_id = self._record_id_from_doi(doi)
        if record_id is None:
            return []
        response = requests.get(
            f"{ZENODO_API_BASE}/{record_id}",
            headers=DEFAULT_HEADERS,
            timeout=60,
        )
        response.raise_for_status()
        files = response.json().get("files") or []
        return [self._normalize_file(raw) for raw in files]

    def _record_id_from_doi(self, doi: str) -> str | None:
        """Extract the numeric Zenodo record id from a DOI string."""
        match = _ZENODO_RECORD_RE.search(doi)
        if not match:
            return None
        return match.group(1)

    def _normalize_file(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Convert a Zenodo file record to the shared inventory shape."""
        links = raw.get("links") or {}
        return {
            "name": str(raw.get("key") or "file"),
            "url": str(links.get("self") or links.get("download") or ""),
            "size_bytes": int(raw.get("size") or 0),
            "source": "zenodo",
        }
