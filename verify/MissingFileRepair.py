"""
Repair DataLumos uploads missing catalog publication files.

When the published view has fewer files than Storage, compares USFS catalog
publication filenames to DataLumos view names, downloads any missing files
into the project folder (skipping those already on disk), and uploads them
to the existing DataLumos project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from playwright.sync_api import Page

from collectors.UsfsAria2Export import (
    Aria2Entry,
    MAX_DOWNLOAD_BYTES,
    format_windows_command,
    is_usfs_catalog_maintenance_page,
    max_connections_for_url,
    run_aria2_cmd_line_with_retries,
)
from collectors.UsfsMetadataExtractor import parse_data_access_links
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from upload.DataLumosFileUploader import DataLumosFileUploader
from utils.Args import Args
from utils.download_with_progress import download_via_url
from utils.file_utils import sanitize_filename
from utils.Logger import Logger
from utils.project_utils import get_field
from utils.url_utils import (
    BROWSER_HEADERS,
    _fetch_html_with_playwright_page,
    fetch_page_body,
)
from verify.DatalumosViewFileStats import DatalumosViewFileStats

PublicationFile = Tuple[str, str, Optional[int]]
STATUS_RE_UPLOADED = "re-uploaded"
WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"
_DOWNLOAD_TIMEOUT_SEC = 3600
_UPLOAD_TIMEOUT_MS = 2 * 60 * 60 * 1000


def should_attempt_missing_file_repair(
    db_num_files: Optional[int],
    page_stats: DatalumosViewFileStats,
) -> bool:
    """
    Return True when DataLumos has fewer files than the database expects.

    Args:
        db_num_files: Expected file count from Storage.
        page_stats: Stats extracted from the DataLumos view page.

    Returns:
        True when a missing-file repair may apply.
    """
    if page_stats.error:
        return False
    if db_num_files is None:
        return False
    return page_stats.file_count < db_num_files


def resolve_project_folder(drpid: int, folder_path: str | None) -> Path:
    """
    Resolve the local download/upload folder for a project.

    Args:
        drpid: Project DRPID.
        folder_path: Stored folder path, if any.

    Returns:
        Absolute folder path (``folder_path`` or ``base_output_dir/DRP######``).
    """
    if folder_path:
        return Path(folder_path)
    return Path(Args.base_output_dir) / f"DRP{drpid:06d}"


def _name_key(name: str) -> str:
    """Normalize a filename for case-insensitive comparison."""
    return sanitize_filename(name).casefold()


def missing_publication_files(
    publication_files: Sequence[PublicationFile],
    dl_names: Sequence[str],
) -> List[PublicationFile]:
    """
    Return catalog publication files whose names are absent from DataLumos.

    Args:
        publication_files: ``(filename, url, size_bytes)`` from the catalog.
        dl_names: Filenames listed on the DataLumos view page.

    Returns:
        Catalog entries not present on DataLumos (by sanitized name).
    """
    present = {_name_key(name) for name in dl_names}
    missing: List[PublicationFile] = []
    for filename, file_url, catalog_bytes in publication_files:
        if _name_key(filename) in present:
            continue
        missing.append((filename, file_url, catalog_bytes))
    return missing


def _publication_files_from_html(html: str, source_url: str) -> List[PublicationFile]:
    """
    Parse publication files from catalog HTML, rejecting maintenance pages.

    Args:
        html: Catalog page HTML.
        source_url: Catalog URL used to resolve relative links.

    Returns:
        Publication file tuples.

    Raises:
        RuntimeError: When the catalog reports maintenance.
    """
    if is_usfs_catalog_maintenance_page(html):
        raise RuntimeError("USFS catalog is under maintenance")
    links = parse_data_access_links(html, source_url)
    return list(links.get("publication_files") or [])


def fetch_catalog_publication_files(
    source_url: str,
    *,
    page: Optional[Page] = None,
) -> List[PublicationFile]:
    """
    Fetch the USFS catalog page and return publication file entries.

    Uses HTTP first. When that yields no publication links and ``page`` is set,
    retries via the existing Playwright page (avoids starting a second Sync API
    session while DataLumosBrowserSession is already open).

    Args:
        source_url: Project catalog URL.
        page: Optional existing Playwright page for fallback fetch.

    Returns:
        Publication file tuples from Data Access links.

    Raises:
        RuntimeError: When the catalog cannot be fetched or is under maintenance.
    """
    status, body, _, _ = fetch_page_body(source_url, timeout=60)
    if status == 200 and body:
        pubs = _publication_files_from_html(body, source_url)
        if pubs:
            return pubs

    if page is None:
        if status != 200 or not body:
            raise RuntimeError(f"catalog fetch failed (status={status})")
        return []

    Logger.info("Catalog HTTP parse empty; retrying with existing browser page")
    pw_status, pw_body, _, _ = _fetch_html_with_playwright_page(page, source_url, 60)
    if pw_status != 200 or not pw_body:
        raise RuntimeError(f"catalog browser fetch failed (status={pw_status})")
    return _publication_files_from_html(pw_body, source_url)


def ensure_file_on_disk(
    folder: Path,
    filename: str,
    file_url: str,
    catalog_bytes: Optional[int],
    *,
    drpid: int,
) -> Path:
    """
    Ensure a publication file exists under ``folder``, downloading when needed.

    Skips download when the sanitized filename is already present (aria2-style).
    Uses aria2 for files >= 1 GB; otherwise HTTP ``download_via_url``.

    Args:
        folder: Destination project folder.
        filename: Catalog filename label.
        file_url: Download URL.
        catalog_bytes: Optional size from the catalog.
        drpid: Project DRPID (for aria2 log paths).

    Returns:
        Path to the on-disk file.

    Raises:
        RuntimeError: When download fails.
    """
    out_name = sanitize_filename(filename)
    dest = folder / out_name
    if dest.is_file():
        Logger.info("Using on-disk file for re-upload: %s", dest)
        return dest

    folder.mkdir(parents=True, exist_ok=True)
    Logger.info("Downloading missing file for re-upload: %s", out_name)

    if catalog_bytes is not None and catalog_bytes >= MAX_DOWNLOAD_BYTES:
        _download_with_aria2(dest, file_url, out_name, drpid=drpid)
    else:
        _bytes_written, success = download_via_url(
            file_url, dest, timeout_sec=_DOWNLOAD_TIMEOUT_SEC
        )
        if not success:
            raise RuntimeError(f"HTTP download failed: {file_url}")

    if not dest.is_file():
        raise RuntimeError(f"download produced no file: {dest}")
    return dest


def _download_with_aria2(
    dest: Path,
    file_url: str,
    out_name: str,
    *,
    drpid: int,
) -> None:
    """Download one large file with aria2c."""
    entry = Aria2Entry(
        url=file_url,
        out_name=out_name,
        dir_path=dest.parent.resolve(),
        max_connections=max_connections_for_url(file_url),
    )
    cmd_line = format_windows_command(entry, BROWSER_HEADERS["User-Agent"])
    log_root = Path(Args.base_output_dir) / "logs" / f"DRP{drpid:06d}"
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / f"{out_name}.log"
    ok, attempts = run_aria2_cmd_line_with_retries(cmd_line, log_path=log_path)
    if not ok:
        raise RuntimeError(
            f"aria2 download failed for {out_name} after {attempts} attempt(s); "
            f"see {log_path}"
        )


def project_workspace_url(workspace_id: str) -> str:
    """
    Build the DataLumos workspace URL for an existing project.

    Args:
        workspace_id: DataLumos project id.

    Returns:
        Workspace deep-link URL.
    """
    return (
        f"{WORKSPACE_URL}?goToLevel=project&goToPath=/datalumos/{workspace_id}#"
    )


class MissingFileRepair:
    """Download and upload catalog files missing from a DataLumos project."""

    def __init__(self, session: DataLumosBrowserSession) -> None:
        """
        Initialize repair helper.

        Args:
            session: Shared authenticated DataLumos browser session.
        """
        self._session = session

    def repair(
        self,
        drpid: int,
        project: Dict[str, Any],
        page_stats: DatalumosViewFileStats,
    ) -> bool:
        """
        Repair missing uploads for one project.

        Args:
            drpid: Project DRPID.
            project: Storage project record.
            page_stats: DataLumos view stats including ``file_names``.

        Returns:
            True when missing files were downloaded (as needed) and uploaded.
        """
        source_url = (get_field(project, "source_url") or "").strip()
        if not source_url:
            Logger.warning("DRPID %s: cannot repair — missing source_url", drpid)
            return False

        workspace_id = (get_field(project, "datalumos_id") or "").strip()
        if not workspace_id:
            Logger.warning("DRPID %s: cannot repair — missing datalumos_id", drpid)
            return False

        browser_page = self._session.ensure_browser()
        publication_files = fetch_catalog_publication_files(
            source_url, page=browser_page
        )
        missing = missing_publication_files(publication_files, page_stats.file_names)
        if not missing:
            Logger.info(
                "DRPID %s: DL file count low but no catalog files missing from DL names",
                drpid,
            )
            return False

        folder = resolve_project_folder(drpid, get_field(project, "folder_path") or None)
        Logger.info(
            "DRPID %s: repairing %s missing file(s) into %s: %s",
            drpid,
            len(missing),
            folder,
            ", ".join(sanitize_filename(name) for name, _, _ in missing),
        )

        paths = [
            ensure_file_on_disk(
                folder,
                filename,
                file_url,
                catalog_bytes,
                drpid=drpid,
            )
            for filename, file_url, catalog_bytes in missing
        ]

        # Long downloads can expire the DataLumos session — refresh before upload.
        self._session.reauthenticate()
        self._upload_paths(workspace_id, paths)
        # Refresh again so the next verify_upload project starts with a good session.
        self._session.reauthenticate()
        return True

    def _upload_paths(self, workspace_id: str, file_paths: List[Path]) -> None:
        """
        Upload files to an existing DataLumos project via the workspace UI.

        Args:
            workspace_id: DataLumos project id.
            file_paths: Local files to upload.
        """
        page = self._session.ensure_browser()
        project_url = project_workspace_url(workspace_id)
        Logger.info("Navigating to DataLumos project %s for re-upload", workspace_id)
        page.goto(project_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=120000)

        from upload.DataLumosAuthenticator import wait_for_human_verification

        wait_for_human_verification(page, timeout=60000)

        page.context.set_default_timeout(_UPLOAD_TIMEOUT_MS)
        uploader = DataLumosFileUploader(
            page,
            timeout=_UPLOAD_TIMEOUT_MS,
            upload_wait_timeout=_UPLOAD_TIMEOUT_MS,
            skip_busy_wait_on_close=True,
        )
        uploader.upload_file_paths(file_paths)
