"""
Upload large files module.

For projects at ``uploaded - large file`` (below ``--max-project-size``, default
25 GB) or ``uploaded - expanded`` (any size): download missing large publication files (aria2, or Chrome Range
chunks for ROSA P), then upload them to the existing DataLumos project.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from collectors.UsfsAria2Export import (
    DEFAULT_ARIA2_MAX_ATTEMPTS,
    DEFAULT_ARIA2_OUTPUT_DIR,
    MAX_DOWNLOAD_BYTES,
    download_exported_cmd_line,
    download_failure_message,
    drpid_cmd_path,
    entries_for_publication_files,
    out_name_from_aria2_cmd_line,
    parse_aria2c_lines_from_cmd_file,
    write_drpid_aria2_cmd,
    aria2_cmd_download_parts,
)
from collectors.UsfsMetadataExtractor import parse_data_access_links
from storage import Storage
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from upload.UploadIssueReporter import UploadIssueReporter
from collectors.SkipNoteFiles import parse_skip_note_download_targets
from utils.Args import Args
from utils.Errors import ProjectAbort, record_crash
from utils.file_utils import (
    format_file_size,
    output_folder_name,
    parse_file_size_to_bytes,
    sanitize_filename,
)
from utils.Logger import Logger
from utils.project_utils import get_field
from utils.url_utils import BROWSER_HEADERS, fetch_page_body

STATUS_UPLOADED_LARGE_FILE = "uploaded - large file"
STATUS_UPLOADED_EXPANDED = "uploaded - expanded"
STATUS_FINISH_WAIT = "finish wait"
UPLOAD_LARGE_FILES_STATUSES = (STATUS_UPLOADED_LARGE_FILE, STATUS_UPLOADED_EXPANDED)
MAX_PROJECT_FILE_SIZE_BYTES = 25 * 1024**3
_BARE_GIGABYTES_RE = re.compile(r"^\d+(?:\.\d+)?$")
DEFAULT_SUMMARY_INTERVAL = 0
UPLOAD_LARGE_FILES_TIMEOUT_MS = 2 * 60 * 60 * 1000  # 2 hours per file / UI action
DISK_SPACE_BUFFER_BYTES = 50 * 1024**3
WORKSPACE_LOAD_TIMEOUT_MS = 60 * 60 * 1000  # workspace navigation after the load event


def parse_max_project_size(value: str | int | float) -> int:
    """
    Return a project-size cap in bytes.

    A bare number is gigabytes (``40`` or ``40.5``). Values with a unit, such as
    ``40GB``, use the same parser as ``projects.file_size``.
    """
    if isinstance(value, bool) or (isinstance(value, (int, float)) and value <= 0):
        raise ValueError(f"max project size must be positive, got {value!r}")
    if isinstance(value, (int, float)):
        return int(float(value) * 1024**3)
    text = str(value).strip()
    if not text:
        raise ValueError("max project size is empty")
    if _BARE_GIGABYTES_RE.match(text):
        return parse_max_project_size(float(text))
    parsed = parse_file_size_to_bytes(text)
    if parsed is None or parsed <= 0:
        raise ValueError(
            f"Invalid max project size {text!r}; use gigabytes (40) or a size (40GB)"
        )
    return parsed


def resolved_max_project_size_bytes() -> int:
    """Return the configured upload_large_files cap, or 25 GB when unset."""
    try:
        raw = getattr(Args, "max_project_size", None)
    except RuntimeError:
        return MAX_PROJECT_FILE_SIZE_BYTES
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return MAX_PROJECT_FILE_SIZE_BYTES
    return parse_max_project_size(raw)


def project_under_size_limit(project: Dict[str, Any]) -> bool:
    """Return True when ``file_size`` is present and below the configured cap."""
    size_bytes = parse_file_size_to_bytes(project.get("file_size"))
    if size_bytes is None:
        return False
    return size_bytes < resolved_max_project_size_bytes()


def is_eligible_for_upload_large_files(project: Dict[str, Any]) -> bool:
    """
    Return True when a project may run ``upload_large_files``.

    ``uploaded - expanded``: any ``file_size``.
    ``uploaded - large file``: ``file_size`` must be present and below
    ``--max-project-size`` (default 25 GB).
    """
    status = (project.get("status") or "").strip()
    if status == STATUS_UPLOADED_EXPANDED:
        return True
    if status == STATUS_UPLOADED_LARGE_FILE:
        return project_under_size_limit(project)
    return False


def resolve_output_folder(drpid: int, folder_path: str | None) -> Path:
    if folder_path:
        return Path(folder_path)
    return Path(Args.base_output_dir) / output_folder_name(drpid)


def log_path_for_download(log_root: Path, drpid: int, out_name: str) -> Path:
    safe = re.sub(r'[<>:"/\\|?*]', "_", out_name)
    return log_root / output_folder_name(drpid) / f"{safe}.log"


def _sizes_from_status_notes(status_notes: str | None) -> Dict[str, int]:
    """Map download filenames from skip notes to byte sizes."""
    sizes: Dict[str, int] = {}
    for name, _url, size_bytes, _folder in parse_skip_note_download_targets(status_notes):
        if size_bytes is None:
            continue
        sizes[name] = size_bytes
        sizes[sanitize_filename(name)] = size_bytes
    return sizes


def _tree_bytes(folder: Path) -> int:
    """Return total size of files under ``folder``."""
    if not folder.is_dir():
        return 0
    total = 0
    for path in folder.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def bytes_still_to_download(
    project: Dict[str, Any],
    folder: Path,
    paths: Sequence[Path],
) -> int:
    """
    Return bytes that large-file download will still write for this project.

    Uses skip-note sizes when every planned file has one. Otherwise uses
    ``file_size`` minus bytes already in the project folder.
    """
    sizes = _sizes_from_status_notes(get_field(project, "status_notes"))
    missing_size = [
        path.name for path in paths if path.name not in sizes and not path.is_file()
    ]
    if not missing_size:
        needed = 0
        for path in paths:
            expected = sizes.get(path.name)
            have = path.stat().st_size if path.is_file() else 0
            if expected is None:
                continue
            needed += max(0, expected - have)
        return needed

    declared = parse_file_size_to_bytes(project.get("file_size"))
    if declared is None:
        record_crash(
            "Cannot determine download size for "
            + ", ".join(missing_size)
            + "; refusing to start the download"
        )
    return max(0, declared - _tree_bytes(folder))


def ensure_disk_space_for_download(folder: Path, needed_bytes: int) -> None:
    """
    Stop the batch when the download would leave less than 50 GB free.

    Args:
        folder: Directory the files will be written under.
        needed_bytes: Bytes still to write. No check when this is zero.

    Raises:
        PipelineFatal: When free space is below ``needed_bytes`` plus 50 GB.
    """
    if needed_bytes <= 0:
        return
    free = shutil.disk_usage(folder).free
    required = needed_bytes + DISK_SPACE_BUFFER_BYTES
    if free >= required:
        return
    record_crash(
        f"Not enough disk space to download project files into {folder}: "
        f"need {format_file_size(required)} "
        f"({format_file_size(needed_bytes)} still to download plus "
        f"{format_file_size(DISK_SPACE_BUFFER_BYTES)} free), "
        f"{format_file_size(free)} free"
    )


def planned_download_paths(aria2_lines: Sequence[str]) -> List[Path]:
    """Return on-disk paths from each aria2 ``-d`` directory and ``-o`` name."""
    paths: List[Path] = []
    for line in aria2_lines:
        _url, dir_path, out_name = aria2_cmd_download_parts(line)
        paths.append(dir_path / out_name)
    return paths


def _path_for_log(folder: Path, path: Path) -> str:
    """Return a project-relative path for logs, or the full path."""
    try:
        return path.resolve().relative_to(folder.resolve()).as_posix()
    except ValueError:
        return str(path)


def planned_out_names(aria2_lines: Sequence[str]) -> List[str]:
    """Extract output filenames from aria2 command lines."""
    names: List[str] = []
    for line in aria2_lines:
        name = out_name_from_aria2_cmd_line(line)
        if name:
            names.append(name)
    return names


def large_files_on_disk(drpid: int, project: Dict[str, Any]) -> List[str]:
    """
    Return catalog-listed large publication filenames that exist on disk.

    Used when there is nothing left to download but large files still need
    uploading to DataLumos.
    """
    source_url = get_field(project, "source_url")
    if not source_url:
        return []

    status, body, _, _ = fetch_page_body(source_url)
    if status != 200 or not body:
        return []

    links = parse_data_access_links(body, source_url)
    folder = resolve_output_folder(drpid, get_field(project, "folder_path") or None)
    entries = entries_for_publication_files(
        links.get("publication_files", []),
        folder,
        min_bytes=MAX_DOWNLOAD_BYTES,
        missing_only=False,
    )
    return [entry.out_name for entry in entries if (folder / entry.out_name).is_file()]


def ensure_aria2_cmd(drpid: int, project: Dict[str, Any]) -> Tuple[Path, List[str]]:
    """
    Ensure ``aria2_inputs/DRP######.cmd`` exists and return its aria2c lines.

    Creates the batch file from the USFS catalog when missing or empty.
    """
    cmd_path = drpid_cmd_path(drpid, DEFAULT_ARIA2_OUTPUT_DIR)
    if cmd_path.is_file():
        lines = parse_aria2c_lines_from_cmd_file(cmd_path)
        if lines:
            return cmd_path, lines

    source_url = get_field(project, "source_url")
    if not source_url:
        return cmd_path, []

    status, body, _, _ = fetch_page_body(source_url)
    if status != 200 or not body:
        Logger.warning(
            "Could not fetch catalog for DRPID=%s to build aria2 cmd (status=%s)",
            drpid,
            status,
        )
        return cmd_path, []

    links = parse_data_access_links(body, source_url)
    folder = resolve_output_folder(drpid, get_field(project, "folder_path") or None)
    folder.mkdir(parents=True, exist_ok=True)

    publication_files = links.get("publication_files", [])
    from_skip_notes = False
    if not publication_files:
        from collectors.NpsAria2Export import write_nps_aria2_cmd_from_notes
        from collectors.SkipNoteFiles import parse_skip_note_download_targets

        targets = parse_skip_note_download_targets(get_field(project, "status_notes"))
        if _skip_targets_need_subfolders(targets):
            write_nps_aria2_cmd_from_notes(
                drpid,
                folder,
                get_field(project, "status_notes"),
                output_dir=DEFAULT_ARIA2_OUTPUT_DIR,
            )
            if not cmd_path.is_file():
                return cmd_path, []
            return cmd_path, parse_aria2c_lines_from_cmd_file(cmd_path)
        publication_files = [
            (name, url, size_bytes) for name, url, size_bytes, _folder in targets
        ]
        from_skip_notes = bool(publication_files)

    write_drpid_aria2_cmd(
        drpid,
        folder,
        publication_files,
        output_dir=DEFAULT_ARIA2_OUTPUT_DIR,
        user_agent=BROWSER_HEADERS["User-Agent"],
        min_bytes=0 if from_skip_notes else MAX_DOWNLOAD_BYTES,
    )

    if not cmd_path.is_file():
        return cmd_path, []
    return cmd_path, parse_aria2c_lines_from_cmd_file(cmd_path)


def _skip_targets_need_subfolders(
    targets: list[tuple[str, str, int | None, str]],
) -> bool:
    """Return True when skip notes name a subfolder or an IRMA download URL."""
    for _name, url, _size, folder in targets:
        if folder or "irma.nps.gov" in url.lower():
            return True
    return False


def run_aria2_downloads(
    drpid: int,
    aria2_lines: Sequence[str],
    *,
    log_root: Path,
    summary_interval: int = DEFAULT_SUMMARY_INTERVAL,
    stop_on_error: bool = True,
    max_attempts: int = DEFAULT_ARIA2_MAX_ATTEMPTS,
) -> Tuple[int, int]:
    """
    Download files listed in exported aria2 command lines.

    Uses Chrome Range chunks for ROSA P URLs (aria2 gets HTTP 403; long
    browser streams truncate); aria2 otherwise.

    Returns:
        (ok_count, fail_count)
    """
    log_dir = log_root / output_folder_name(drpid)
    log_dir.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    fail_count = 0
    for index, cmd_line in enumerate(aria2_lines, start=1):
        out_name = out_name_from_aria2_cmd_line(cmd_line) or f"download_{index}"
        log_path = log_path_for_download(log_root, drpid, out_name)

        if len(aria2_lines) > 1:
            Logger.info("[%s/%s] Downloading %s", index, len(aria2_lines), out_name)

        ok, attempts = download_exported_cmd_line(
            cmd_line,
            log_path=log_path,
            summary_interval=summary_interval,
            max_attempts=max_attempts,
            page_downloader=None,
        )
        if ok:
            ok_count += 1
            if attempts > 1:
                Logger.info(
                    "Download succeeded for DRPID=%s file=%s after %s attempt(s)",
                    drpid,
                    out_name,
                    attempts,
                )
        else:
            fail_count += 1
            Logger.error(
                "Download failed for DRPID=%s file=%s after %s attempt(s) log=%s",
                drpid,
                out_name,
                attempts,
                log_path,
            )
            if stop_on_error:
                break

    if fail_count:
        Logger.error(
            "DRPID=%s downloads: %s ok, %s failed — logs in %s",
            drpid,
            ok_count,
            fail_count,
            log_dir,
        )
    return ok_count, fail_count


class UploadLargeFiles:
    """
    Download missing large files and upload them to an existing DataLumos project.

    Prerequisites: ``uploaded - large file`` with ``file_size`` below
    ``--max-project-size`` (default 25 GB), or ``uploaded - expanded`` at any
    size; no errors
    Success status: ``finish wait``
    """

    WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"

    def __init__(self) -> None:
        self._session = DataLumosBrowserSession()

    def run(self, drpid: int) -> None:
        Logger.info("Starting upload_large_files for DRPID=%s", drpid)
        reporter = UploadIssueReporter(drpid)

        project = Storage.get(drpid)
        if project is None:
            reporter.error(f"Project with DRPID={drpid} not found in Storage")
            return

        status = (project.get("status") or "").strip()
        if status not in UPLOAD_LARGE_FILES_STATUSES:
            reporter.error(
                f"Expected status in {UPLOAD_LARGE_FILES_STATUSES!r}, got {status!r}"
            )
            return

        if status == STATUS_UPLOADED_LARGE_FILE and not project_under_size_limit(project):
            cap = format_file_size(resolved_max_project_size_bytes())
            reporter.error(
                f"Project file_size is missing or >= {cap}; skipping large-file upload"
            )
            return

        errors = self._validate_project(project)
        if errors:
            for error in errors:
                reporter.error(error)
            return

        folder = resolve_output_folder(drpid, get_field(project, "folder_path") or None)
        if not folder.is_dir():
            reporter.error(f"Folder path is not a directory: {folder}")
            return

        try:
            _, aria2_lines = ensure_aria2_cmd(drpid, project)
            download_paths = planned_download_paths(aria2_lines)

            if aria2_lines:
                needed_bytes = bytes_still_to_download(project, folder, download_paths)
                ensure_disk_space_for_download(folder, needed_bytes)
                log_root = Path(Args.base_output_dir) / "logs"
                _, fail_count = run_aria2_downloads(drpid, aria2_lines, log_root=log_root)
                if fail_count:
                    reporter.error(
                        download_failure_message(
                            f"Large-file download failed for {fail_count} file(s); "
                            f"see logs under {log_root}"
                        )
                    )
                    return

            upload_paths = download_paths or [
                folder / name for name in large_files_on_disk(drpid, project)
            ]
            if not upload_paths:
                reporter.error(
                    "No large files to upload (nothing to download and none found on disk)"
                )
                return

            missing = [str(path) for path in upload_paths if not path.is_file()]
            if missing:
                reporter.error(f"Missing expected file(s) on disk: {', '.join(missing)}")
                return

            Logger.info(
                "Uploading %s large file(s) for DRPID=%s: %s",
                len(upload_paths),
                drpid,
                ", ".join(_path_for_log(folder, path) for path in upload_paths),
            )
            self._upload_files_to_existing_project(
                project, drpid, folder, upload_paths, reporter
            )
            Storage.update_record(drpid, {"status": STATUS_FINISH_WAIT})
            Logger.info(
                "upload_large_files completed for DRPID=%s, status=%s",
                drpid,
                STATUS_FINISH_WAIT,
            )
        except ProjectAbort:
            return
        except Exception as exc:
            reporter.error(f"upload_large_files failed: {exc}")
            raise
        finally:
            self._session.close()

    def _validate_project(self, project: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not get_field(project, "datalumos_id"):
            errors.append("Missing datalumos_id; project must be uploaded before large files")
        folder = get_field(project, "folder_path")
        if folder:
            path = Path(folder)
            if not path.exists():
                errors.append(f"Folder path does not exist: {folder}")
            elif not path.is_dir():
                errors.append(f"Folder path is not a directory: {folder}")
        return errors

    def _project_url(self, workspace_id: str) -> str:
        return f"{self.WORKSPACE_URL}?goToLevel=project&goToPath=/datalumos/{workspace_id}#"

    def _upload_files_to_existing_project(
        self,
        project: Dict[str, Any],
        drpid: int,
        folder: Path,
        file_paths: List[Path],
        reporter: UploadIssueReporter,
    ) -> None:
        workspace_id = get_field(project, "datalumos_id")
        page = self._session.ensure_browser()
        self._session.ensure_authenticated(reporter=reporter)

        project_url = self._project_url(workspace_id)
        Logger.info("Navigating to existing DataLumos project %s", workspace_id)
        page.goto(project_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=WORKSPACE_LOAD_TIMEOUT_MS)

        from upload.DataLumosAuthenticator import wait_for_human_verification

        wait_for_human_verification(page, timeout=60000, reporter=reporter)

        from upload.DataLumosFileUploader import DataLumosFileUploader

        page.context.set_default_timeout(UPLOAD_LARGE_FILES_TIMEOUT_MS)
        file_uploader = DataLumosFileUploader(
            page,
            timeout=UPLOAD_LARGE_FILES_TIMEOUT_MS,
            upload_wait_timeout=UPLOAD_LARGE_FILES_TIMEOUT_MS,
            reporter=reporter,
            skip_busy_wait_on_close=True,
        )
        file_uploader.upload_paths_preserving_folders(folder, file_paths)
