"""
Post project files through the deposit API.

The Upload button opens a Dropzone modal whose request is
``POST /uploadRawFile``. Import From Zip is ``POST /uploadZipFile``.
Both send the bearer token already saved for the browser session, so the
project page does not have to load.
"""

from __future__ import annotations

import mimetypes
import os
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import Page

from upload.DataLumosFileUploader import (
    PARALLEL_FILE_UPLOADS,
    queue_wait_timeout_ms,
)
from upload.deposit_direct import parse_body
from upload.deposit_page_request import DEPOSIT_SERVER, redact_secrets
from utils.file_utils import format_file_size
from utils.Logger import Logger

_QUEUE_TIMEOUT_MS = 600000


class DepositFileUpload:
    """Upload one project's files with the deposit bearer token."""

    def __init__(self, page: Page, token: str, timeout_ms: int = _QUEUE_TIMEOUT_MS) -> None:
        """
        Args:
            page: Authenticated Playwright page. Its cookie jar is copied onto each POST.
            token: Bearer token already read for this browser session.
            timeout_ms: How long to wait for the server to accept one file.
        """
        self._page = page
        self._token = token or ""
        self._timeout_ms = timeout_ms
        self._cookie_records: list[dict[str, str]] = []

    @property
    def token(self) -> str:
        """Bearer token for this client, empty after a rejected response."""
        return self._token

    def upload_folder(self, workspace_id: str, folder_path: str) -> None:
        """Upload a project folder. Subfolders go through Import From Zip."""
        self._load_cookies()
        folder = Path(folder_path)
        if not folder.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {folder_path}")
        if any(path.is_dir() for path in folder.iterdir()):
            self._upload_zip_folder(workspace_id, folder)
            return
        files = [path for path in folder.iterdir() if path.is_file()]
        if not files:
            Logger.info("No files to upload in %s", folder_path)
            return
        self.upload_files(workspace_id, files)

    def upload_files(self, workspace_id: str, files: list[Path]) -> None:
        """POST each file to ``/uploadRawFile``, four at a time."""
        self._load_cookies()
        total = len(files)
        start = 0
        while start < total:
            batch = files[start : start + PARALLEL_FILE_UPLOADS]
            self._upload_batch(workspace_id, batch, start, total)
            start += len(batch)

    def _upload_zip_folder(self, workspace_id: str, folder: Path) -> None:
        """Zip the folder and POST it to ``/uploadZipFile``."""
        zip_path = _zip_folder(folder)
        try:
            Logger.info("Uploading zip via deposit API: %s", zip_path.name)
            self._upload_one(workspace_id, zip_path, zip_upload=True)
        finally:
            zip_path.unlink(missing_ok=True)

    def _upload_batch(
        self,
        workspace_id: str,
        batch: list[Path],
        start: int,
        total: int,
    ) -> None:
        """POST one group of files and raise the first rejection."""
        self._announce_batch(batch, start, total)
        errors = self._post_batch(workspace_id, batch)
        if errors:
            raise RuntimeError(errors[0])

    def _announce_batch(self, batch: list[Path], start: int, total: int) -> None:
        """Log each file in a parallel group before any of them are sent."""
        for offset, path in enumerate(batch, start=start + 1):
            Logger.info(
                "uploading file %s of %s (%s)",
                offset,
                total,
                format_file_size(path.stat().st_size),
            )

    def _post_batch(self, workspace_id: str, batch: list[Path]) -> list[str]:
        """POST every file in the group. Returns rejection messages."""
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            futures = [
                pool.submit(self._upload_one, workspace_id, path, zip_upload=False)
                for path in batch
            ]
            for future in futures:
                errors.extend(_future_error(future))
        return errors

    def _upload_one(self, workspace_id: str, path: Path, *, zip_upload: bool) -> None:
        """POST one file and require the queued or zip-accepted response."""
        if not self._token:
            raise RuntimeError("Deposit token is missing")
        endpoint = "uploadZipFile" if zip_upload else "uploadRawFile"
        timeout_s = queue_wait_timeout_ms(self._timeout_ms, path.stat().st_size) / 1000
        started = time.perf_counter()
        try:
            response = self._post(upload_url(workspace_id, path, zip_upload=zip_upload), path, timeout_s)
        except requests.RequestException as exc:
            raise RuntimeError(f"Deposit POST /deposit/{endpoint} failed ({exc})") from exc
        Logger.info(
            "Deposit POST /deposit/%s -> %s in %.1fs",
            endpoint,
            response.status_code,
            time.perf_counter() - started,
        )
        if response.status_code == 401:
            self._token = ""
        interpret_upload_response(response.status_code, response.text, endpoint)

    def _load_cookies(self) -> None:
        """Copy the browser cookies on this thread, before any worker starts.

        Playwright's sync client belongs to the calling thread. Workers only
        receive the copied records.
        """
        self._cookie_records = _cookie_records(self._page)

    def _post(self, url: str, path: Path, timeout_s: float) -> requests.Response:
        """Stream one file as the multipart field ``file``."""
        with path.open("rb") as handle:
            return requests.post(
                url,
                headers={"Authorization": f"Bearer {self._token}"},
                cookies=_jar_from_records(self._cookie_records),
                files={"file": (path.name, handle, mime_type(path))},
                timeout=timeout_s,
            )


def upload_url(workspace_id: str, path: Path, *, zip_upload: bool) -> str:
    """Build the Dropzone URL for one file.

    The modal concatenates the project path, the file's last-modified time in
    milliseconds, and its MIME type without encoding them.
    """
    endpoint = "uploadZipFile" if zip_upload else "uploadRawFile"
    modified_ms = int(path.stat().st_mtime * 1000)
    resource = f"/datalumos/{workspace_id}"
    return (
        f"{DEPOSIT_SERVER}/{endpoint}?resourceId={resource}"
        f"&lastModified={modified_ms}&type={mime_type(path)}"
    )


def interpret_upload_response(status: int, body_text: str, endpoint: str) -> None:
    """Raise unless the body is the modal's queued or zip-accepted payload."""
    if status < 200 or status >= 300:
        detail = redact_secrets(body_text)[:300]
        raise RuntimeError(f"Deposit POST /deposit/{endpoint} failed ({status}): {detail}")
    body = parse_body(body_text)
    if body is None or body == "":
        raise RuntimeError("File is already in this project")
    if not isinstance(body, dict):
        detail = redact_secrets(body_text)[:300]
        raise RuntimeError(f"Deposit POST /deposit/{endpoint} returned an unexpected body: {detail}")
    _raise_for_file_status(body)


def mime_type(path: Path) -> str:
    """Return the MIME type Dropzone would send for this filename."""
    guessed, _encoding = mimetypes.guess_type(path.name)
    if path.suffix.lower() == ".zip":
        return guessed or "application/zip"
    return guessed or "application/octet-stream"


def _raise_for_file_status(body: dict[str, Any]) -> None:
    """Raise when the deposit body reports a rejected file."""
    if body.get("type") == "zip":
        return
    file_status = body.get("fileStatus")
    if file_status == "failed":
        raise RuntimeError(str(body.get("description") or "File upload failed"))
    if file_status:
        raise RuntimeError(f"File upload was not queued ({file_status})")


def _zip_folder(folder: Path) -> Path:
    """Zip a project folder. The caller deletes the archive."""
    descriptor, zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(descriptor)
    archive = Path(zip_path)
    shutil.make_archive(str(archive.with_suffix("")), "zip", folder, ".")
    Logger.info("Zipped contents of %s to %s", folder, archive.name)
    return archive


def _cookie_records(page: Page) -> list[dict[str, str]]:
    """Read browser cookies into plain records the worker threads can copy."""
    records: list[dict[str, str]] = []
    for cookie in page.context.cookies():
        records.append(
            {
                "name": str(cookie.get("name") or ""),
                "value": str(cookie.get("value") or ""),
                "domain": str(cookie.get("domain") or ""),
                "path": str(cookie.get("path") or "/"),
            }
        )
    return records


def _jar_from_records(records: list[dict[str, str]]) -> requests.cookies.RequestsCookieJar:
    """Build a private cookie jar from records captured on the caller thread."""
    jar = requests.cookies.RequestsCookieJar()
    for cookie in records:
        if not cookie["name"]:
            continue
        jar.set(
            cookie["name"],
            cookie["value"],
            domain=cookie["domain"] or None,
            path=cookie["path"],
        )
    return jar


def _future_error(future: Any) -> list[str]:
    """Return a worker failure message, or an empty list when it succeeded."""
    try:
        future.result()
    except Exception as exc:
        return [str(exc)]
    return []
