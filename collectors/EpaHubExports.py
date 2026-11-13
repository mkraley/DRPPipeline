"""
Download EDG Clip and Ship service JSON and Hub export files.

Feature services use the site download API. Service definitions use the
ArcGIS item data endpoint. Exports that would pass the 1 GiB budget are
left for a later download.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests

from collectors.BudgetedDownload import BudgetedDownload
from collectors.DataGovFileDownloader import save_arcgis_service_json
from collectors.EpaHubExportPlan import (
    ReadyFile,
    bytes_on_disk,
    close_response,
    content_length,
    file_specs,
    ready_from_response,
)
from collectors.PlannedFile import PlannedFile
from utils.Logger import Logger
from utils.collector_status import (
    MAX_DOWNLOAD_BYTES,
    deferred_download_skip_note,
    would_exceed_download_budget,
)
from utils.url_utils import requests_verify

_STATUS_TIMEOUT = (10, 30)
_DOWNLOAD_TIMEOUT = (10, 300)
_MAX_REQUEST_FAILURES = 3
_MAX_SERVER_ERRORS = 5
_SERVER_ERROR_PAUSE_SEC = 5.0
_RETRYABLE_HTTP = frozenset({500, 502, 503, 504})


class EpaHubExports:
    """Save service metadata and generated open-format exports."""

    def __init__(
        self,
        *,
        getter: Any | None = None,
        sleeper: Any | None = None,
        attempts: int = 150,
        pause_sec: float = 2.0,
    ) -> None:
        """
        Initialize the exporter.

        Args:
            getter: ``requests.get`` replacement for tests.
            sleeper: ``time.sleep`` replacement for tests.
            attempts: How many times to poll a generating export. The default
                waits about five minutes.
            pause_sec: Seconds between polls.
        """
        self._get = getter or requests.get
        self._sleep = sleeper or time.sleep
        self._attempts = attempts
        self._pause_sec = pause_sec

    def download_all(
        self,
        folder: Path,
        feature: dict[str, Any],
    ) -> tuple[list[str], list[PlannedFile]]:
        """
        Save service JSON and export files that fit in the download budget.

        Args:
            folder: Project output folder.
            feature: Hub search feature.

        Returns:
            Status notes and the planned file list, including deferred files.
        """
        notes: list[str] = []
        planned: list[PlannedFile] = []
        downloaded = bytes_on_disk(folder)
        for name, url in file_specs(feature, self._service_payload(folder, feature)):
            kept = self._existing(folder, name, url)
            if kept is not None:
                planned.append(kept)
                downloaded += kept.size_bytes or 0
                continue
            Logger.info("Requesting Hub export %s", name)
            ready = self._resolve(url)
            planned_file, note, written = self._save_ready(
                folder, name, url, ready, downloaded
            )
            planned.append(planned_file)
            if note:
                notes.append(note)
            if written:
                Logger.info("Saved Hub export %s", name)
                downloaded += written
            elif planned_file.access_error:
                Logger.warning(
                    "Hub export %s was not saved: %s",
                    name,
                    planned_file.access_error,
                )
        return notes, planned

    def commit(self, drpid: int, folder: Path, planned: list[PlannedFile]) -> str:
        """
        Store the file inventory and return the collected status.

        Args:
            drpid: Project DRPID.
            folder: Project output folder.
            planned: Files referenced by this collection.

        Returns:
            Collected status from the shared budget helper.
        """
        return BudgetedDownload().commit_inventory(drpid, folder, planned)

    def _service_payload(self, folder: Path, feature: dict[str, Any]) -> dict[str, Any]:
        """Save FeatureServer JSON when present and return the parsed service."""
        from collectors.EpaHubItem import service_url_from_feature

        service_url = service_url_from_feature(feature)
        if not service_url:
            return {}
        path = save_arcgis_service_json(folder, service_url)
        if path is None:
            return {}
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_ready(
        self,
        folder: Path,
        name: str,
        source_url: str,
        ready: ReadyFile,
        downloaded: int,
    ) -> tuple[PlannedFile, str, int]:
        """Write one ready file or record that it was deferred or failed."""
        file_url = ready.file_url or source_url
        if ready.error:
            return PlannedFile(name, file_url, access_error=ready.error), "", 0
        if would_exceed_download_budget(downloaded, ready.size_bytes) and (
            ready.size_bytes is not None or downloaded >= MAX_DOWNLOAD_BYTES
        ):
            note = deferred_download_skip_note(name, file_url, ready.size_bytes)
            return PlannedFile(name, file_url, ready.size_bytes), note, 0
        dest = folder / name
        if not self._write(file_url, dest):
            return PlannedFile(name, file_url, access_error="download failed"), "", 0
        size = dest.stat().st_size
        return PlannedFile(name, file_url, size), "", size

    def _existing(self, folder: Path, name: str, url: str) -> PlannedFile | None:
        """Return a planned file when ``name`` is already saved."""
        dest = folder / name
        if not dest.is_file() or dest.stat().st_size <= 0:
            return None
        Logger.info("Keeping existing Hub export %s", name)
        return PlannedFile(name, url, dest.stat().st_size)

    def _resolve(self, url: str) -> ReadyFile:
        """Poll until an export is ready, then return its file URL and size."""
        failures = 0
        server_errors = 0
        for _attempt in range(self._attempts):
            ready, failed = self._status(url)
            if failed:
                failures += 1
                if failures >= _MAX_REQUEST_FAILURES:
                    return ReadyFile(url, None, "export request timed out")
                self._sleep(self._pause_sec)
                continue
            failures = 0
            if ready is None:
                self._sleep(self._pause_sec)
                continue
            if self._retry_server_error(ready, server_errors):
                server_errors += 1
                continue
            return self._with_size(ready, url)
        return ReadyFile(url, None, "export was not ready")

    def _status(self, url: str) -> tuple[ReadyFile | None, bool]:
        """Return one status result and whether the request itself failed."""
        response = self._poll(url)
        if response is None:
            return None, True
        return ready_from_response(response), False

    def _retry_server_error(self, ready: ReadyFile, seen: int) -> bool:
        """Pause and try again after a transient Hub server error."""
        if _server_status(ready) is None or seen + 1 >= _MAX_SERVER_ERRORS:
            return False
        Logger.warning("Hub export returned %s; retrying", ready.error)
        self._sleep(_SERVER_ERROR_PAUSE_SEC)
        return True

    def _poll(self, url: str) -> Any | None:
        """GET one export status. None means the request itself failed."""
        try:
            return self._request(url, stream=True, allow_redirects=False)
        except requests.RequestException as exc:
            Logger.warning("Hub export request failed: %s", exc)
            return None

    def _with_size(self, ready: ReadyFile, requested_url: str) -> ReadyFile:
        """Fill in Content-Length when the status body did not include it."""
        if ready.error or ready.size_bytes is not None:
            return ready
        if ready.file_url in {"", requested_url}:
            return ready
        try:
            head = self._request(
                ready.file_url,
                stream=True,
                allow_redirects=True,
                timeout=_DOWNLOAD_TIMEOUT,
            )
        except requests.RequestException as exc:
            Logger.warning("Could not read export size: %s", exc)
            return ready
        size = content_length(head)
        close_response(head)
        return ReadyFile(ready.file_url, size, None)

    def _request(self, url: str, **kwargs: Any) -> Any:
        """GET ``url`` with the configured client."""
        kwargs.setdefault("timeout", _STATUS_TIMEOUT)
        return self._get(
            url,
            verify=requests_verify(),
            headers={"Accept": "*/*"},
            **kwargs,
        )

    def _write(self, url: str, dest: Path) -> bool:
        """Stream ``url`` to ``dest``."""
        try:
            response = self._request(
                url,
                stream=True,
                allow_redirects=True,
                timeout=_DOWNLOAD_TIMEOUT,
            )
        except requests.RequestException as exc:
            Logger.warning("Hub export download failed: %s", exc)
            return False
        try:
            if getattr(response, "status_code", 500) >= 400:
                return False
            return self._write_body(response, dest)
        except requests.RequestException as exc:
            Logger.warning("Hub export download failed: %s", exc)
            dest.unlink(missing_ok=True)
            return False
        finally:
            close_response(response)

    def _write_body(self, response: Any, dest: Path) -> bool:
        """Write a successful response body to ``dest``."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if chunk:
                    handle.write(chunk)
        return dest.is_file() and dest.stat().st_size > 0


def _server_status(ready: ReadyFile) -> int | None:
    """Return a retryable HTTP status from an export error, or None."""
    text = ready.error or ""
    if not text.startswith("export HTTP "):
        return None
    try:
        code = int(text.removeprefix("export HTTP ").split()[0])
    except ValueError:
        return None
    if code in _RETRYABLE_HTTP:
        return code
    return None

