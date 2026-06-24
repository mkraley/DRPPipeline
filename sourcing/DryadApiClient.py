"""
List dataset files from Dryad via the public REST API.

Dryad DOIs use the ``10.5061/dryad.*`` prefix. API docs:
https://github.com/CDL-Dryad/dryad-app/blob/main/documentation/apis/README.md
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests

DRYAD_API_BASE = "https://datadryad.org/api/v2"
DEFAULT_HEADERS = {"User-Agent": "DRPPipeline/1.0", "Accept": "application/json"}


class DryadApiClient:
    """Resolve Dryad dataset DOIs to downloadable file metadata."""

    def list_files_for_doi(self, doi: str) -> list[dict[str, Any]]:
        """
        List files for the latest version of a Dryad dataset DOI.

        Args:
            doi: Full DOI, e.g. ``10.5061/dryad.5hqbzkhcz``.

        Returns:
            Dicts with keys ``name``, ``url``, ``size_bytes``, and ``source``.
        """
        encoded = quote(f"doi:{doi}", safe="")
        dataset_url = f"{DRYAD_API_BASE}/datasets/{encoded}"
        dataset_response = requests.get(dataset_url, headers=DEFAULT_HEADERS, timeout=60)
        dataset_response.raise_for_status()
        versions_href = self._link_href(dataset_response.json(), "stash:versions")
        if not versions_href:
            return []
        versions_response = requests.get(
            self._absolute_url(versions_href),
            headers=DEFAULT_HEADERS,
            timeout=60,
        )
        versions_response.raise_for_status()
        versions = versions_response.json().get("_embedded", {}).get("stash:versions", [])
        if not versions:
            return []
        files_href = self._link_href(versions[-1], "stash:files")
        if not files_href:
            return []
        files_response = requests.get(
            self._absolute_url(files_href),
            headers=DEFAULT_HEADERS,
            timeout=60,
        )
        files_response.raise_for_status()
        raw_files = files_response.json().get("_embedded", {}).get("stash:files", [])
        return [self._normalize_file(raw) for raw in raw_files]

    def _normalize_file(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Convert a Dryad file record to the shared inventory shape."""
        download_href = self._link_href(raw, "stash:download")
        return {
            "name": str(raw.get("path") or "file"),
            "url": self._absolute_url(download_href) if download_href else "",
            "size_bytes": int(raw.get("size") or 0),
            "source": "dryad",
        }

    def _link_href(self, payload: dict[str, Any], rel: str) -> str:
        """Read a HAL link href from a Dryad API payload."""
        links = payload.get("_links") or {}
        link = links.get(rel) or {}
        return str(link.get("href") or "")

    def _absolute_url(self, href: str) -> str:
        """Join a Dryad API relative href to the API host."""
        if not href:
            return ""
        if href.startswith("http"):
            return href
        return f"https://datadryad.org{href}"
