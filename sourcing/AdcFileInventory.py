"""
Build downloadable-file inventories for Ag Data Commons (ADC) datasets.

Combines Figshare-hosted files with external repository files (Dryad, Zenodo)
resolved via public APIs. Used during sourcing and collection.
"""

from __future__ import annotations

from typing import Any

from sourcing.DryadApiClient import DryadApiClient
from sourcing.ZenodoApiClient import ZenodoApiClient
from utils.file_utils import format_file_size

MAX_DOWNLOAD_BYTES = 1 * 1024**3  # 1 GB — collection skips larger files (USFS pattern)
_KNOWN_SOURCES = frozenset({"figshare", "dryad", "zenodo"})


class AdcFileInventory:
    """Resolve ADC/Figshare articles to a normalized file inventory."""

    def __init__(self) -> None:
        """Initialize external repository clients."""
        self._dryad = DryadApiClient()
        self._zenodo = ZenodoApiClient()

    def list_files_for_article(self, article: dict[str, Any]) -> list[dict[str, Any]]:
        """
        List downloadable files for one Figshare article.

        Hosted Figshare files are taken from ``article['files']``. Zero-byte
        placeholder files with external DOI links are expanded via Dryad/Zenodo APIs.

        Args:
            article: Full Figshare article JSON.

        Returns:
            Normalized file dicts with ``name``, ``url``, ``size_bytes``, ``source``.
        """
        files = article.get("files") or []
        if not files:
            return []
        if self._needs_external_resolution(files):
            external = self._resolve_external_files(article, files)
            if external:
                return external
        return [self._normalize_figshare_file(raw) for raw in files]

    def summarize_inventory(
        self,
        files: list[dict[str, Any]],
    ) -> tuple[int, str, str, bool, bool, bool]:
        """
        Summarize inventory for Storage numeric fields.

        Returns:
            Tuple of (num_files, formatted total size, comma-separated extensions,
            has_large_file, has_unresolved_external, all_external_unresolved).
        """
        num_files, file_size, extensions, has_large, _total_bytes, has_unresolved = (
            self._measure_inventory(files)
        )
        all_unresolved = bool(files) and all(
            str(file_row.get("source") or "") == "external-unresolved" for file_row in files
        )
        return num_files, file_size, extensions, has_large, has_unresolved, all_unresolved

    def classify_hosting(self, article: dict[str, Any]) -> str:
        """
        Classify where an ADC record's downloadable data is hosted.

        Returns:
            One of ``figshare``, ``dryad``, ``zenodo``, ``external-unresolved``,
            or ``none``.
        """
        doi = str(article.get("doi") or "")
        if doi.startswith("10.5061/dryad."):
            return "dryad"
        if doi.startswith("10.5281/zenodo."):
            return "zenodo"
        if doi.startswith("10.15482/USDA.ADC"):
            return "figshare"
        files = self.list_files_for_article(article)
        if not files:
            return "none"
        sources = {str(file_row.get("source") or "") for file_row in files}
        if sources <= _KNOWN_SOURCES and "external-unresolved" not in sources:
            if "zenodo" in sources:
                return "zenodo"
            if "dryad" in sources:
                return "dryad"
            return "figshare"
        return "external-unresolved"

    def _measure_inventory(
        self,
        files: list[dict[str, Any]],
    ) -> tuple[int, str, str, bool, int, bool]:
        """Compute raw inventory metrics shared by summary formatters."""
        total_bytes = 0
        extensions: set[str] = set()
        has_large = False
        has_unresolved = False
        for file_row in files:
            size_bytes = file_row.get("size_bytes")
            if isinstance(size_bytes, int):
                total_bytes += size_bytes
                if size_bytes > MAX_DOWNLOAD_BYTES:
                    has_large = True
            source = str(file_row.get("source") or "")
            if source == "external-unresolved":
                has_unresolved = True
            name = str(file_row.get("name") or "")
            if "." in name:
                extensions.add(name.rsplit(".", 1)[-1].lower())
        return (
            len(files),
            format_file_size(total_bytes),
            ", ".join(sorted(extensions)),
            has_large,
            total_bytes,
            has_unresolved,
        )

    def _needs_external_resolution(self, files: list[dict[str, Any]]) -> bool:
        """Return True when Figshare only lists zero-byte external DOI placeholders."""
        if len(files) != 1:
            return False
        only = files[0]
        size = int(only.get("size") or 0)
        download_url = str(only.get("download_url") or "")
        return size == 0 and "doi.org" in download_url

    def _resolve_external_files(
        self,
        article: dict[str, Any],
        files: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Expand external repository files for catalog/harvest ADC records."""
        doi = str(article.get("doi") or "")
        if doi.startswith("10.5061/dryad."):
            return self._dryad.list_files_for_doi(doi)
        if doi.startswith("10.5281/zenodo."):
            return self._zenodo.list_files_for_doi(doi)
        placeholder = files[0]
        download_url = str(placeholder.get("download_url") or "")
        return [{
            "name": str(placeholder.get("name") or "external"),
            "url": download_url,
            "size_bytes": 0,
            "source": "external-unresolved",
        }]

    def _normalize_figshare_file(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Convert a Figshare file record to the shared inventory shape."""
        return {
            "name": str(raw.get("name") or "file"),
            "url": str(raw.get("download_url") or ""),
            "size_bytes": int(raw.get("size") or 0),
            "source": "figshare",
        }
