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
FIGSHARE_DOWNLOAD_HOST = "figshare.com"
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

    def has_figshare_hosted_files(self, article: dict[str, Any]) -> bool:
        """
        Return True when the article lists at least one downloadable Figshare file.

        Args:
            article: Full Figshare article JSON.

        Returns:
            True if any file is hosted on Figshare with size > 0.
        """
        return any(
            self._is_figshare_hosted_raw(raw)
            for raw in (article.get("files") or [])
        )

    def is_external_archive(self, article: dict[str, Any]) -> bool:
        """
        Return True when dataset files are not hosted on Figshare.

        External-archive records (link-only URLs, DOI placeholders, empty file
        lists) should not trigger download of outbound links during collection.

        Args:
            article: Full Figshare article JSON.
        """
        return not self.has_figshare_hosted_files(article)

    def list_figshare_hosted_files(self, article: dict[str, Any]) -> list[dict[str, Any]]:
        """
        List only Figshare-hosted files suitable for automatic download.

        Does not follow DOI links or other external repositories.

        Args:
            article: Full Figshare article JSON.

        Returns:
            Normalized inventory rows with ``source`` ``figshare``.
        """
        return [
            self._normalize_figshare_file(raw)
            for raw in (article.get("files") or [])
            if self._is_figshare_hosted_raw(raw)
        ]

    def list_external_reference_urls(self, article: dict[str, Any]) -> list[str]:
        """
        Return outbound URLs listed on an external-archive Figshare article.

        Collects ``download_url`` values from link-only placeholders and other
        non-Figshare file entries without following them.

        Args:
            article: Full Figshare article JSON.

        Returns:
            Unique external URLs in Figshare file order.
        """
        urls: list[str] = []
        seen: set[str] = set()
        for raw in article.get("files") or []:
            if self._is_figshare_hosted_raw(raw):
                continue
            download_url = str(raw.get("download_url") or "").strip()
            if download_url and download_url not in seen:
                seen.add(download_url)
                urls.append(download_url)
        return urls

    def external_archive_status_note(self, article: dict[str, Any]) -> str | None:
        """
        Build a status_notes line for external-archive datasets when URLs are known.

        Args:
            article: Full Figshare article JSON.

        Returns:
            Formatted note text, or None when no external URL is listed.
        """
        urls = self.list_external_reference_urls(article)
        if not urls:
            return None
        if len(urls) == 1:
            return f"External data URL: {urls[0]}"
        return "External data URLs:\n" + "\n".join(urls)

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

    def _is_figshare_hosted_raw(self, raw: dict[str, Any]) -> bool:
        """Return True when a Figshare file record is a hosted, non-link download."""
        size = int(raw.get("size") or 0)
        if size <= 0:
            return False
        download_url = str(raw.get("download_url") or "")
        if FIGSHARE_DOWNLOAD_HOST not in download_url:
            return False
        if raw.get("is_link_only"):
            return False
        return True

    def _normalize_figshare_file(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Convert a Figshare file record to the shared inventory shape."""
        return {
            "name": str(raw.get("name") or "file"),
            "url": str(raw.get("download_url") or ""),
            "size_bytes": int(raw.get("size") or 0),
            "source": "figshare",
        }
