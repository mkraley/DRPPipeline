"""
API module for project operations.

Serves: GET /api/projects/first, /api/projects/next, /api/projects/<drpid>.
Provides project listing, next-eligible lookup, and output folder creation
for the Interactive Collector SPA.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from utils.url_utils import is_valid_url

from interactive_collector.collector_state import get_base_output_dir, get_db_path, get_result_by_drpid


def _ensure_storage() -> None:
    """
    Initialize Storage if not already, using Args.db_path or default.
    Ensures Logger is initialized first. Idempotent.
    """
    from storage import Storage
    try:
        Storage.list_eligible_projects(None, 0)
    except RuntimeError:
        try:
            from utils.Logger import Logger
            if not getattr(Logger, "_initialized", False):
                Logger.initialize(log_level="WARNING")
        except Exception:
            pass
        path = get_db_path()
        Storage.initialize("StorageSQLLite", db_path=path)


def get_first_eligible() -> Optional[Dict[str, Any]]:
    """
    Return the first eligible project (prereq=sourcing, no errors) or None.

    Returns:
        Project dict with DPRID, source_url, etc., or None.
    """
    _ensure_storage()
    from storage import Storage
    projects = Storage.list_eligible_projects("sourced", 1)
    return projects[0] if projects else None


def get_next_eligible_after(current_drpid: int) -> Optional[Dict[str, Any]]:
    """
    Return the next eligible project after current_drpid, or None.

    Args:
        current_drpid: Current project's DRPID.

    Returns:
        Next project dict or None.
    """
    _ensure_storage()
    from storage import Storage
    projects = Storage.list_eligible_projects("sourced", 200)
    for proj in projects:
        if proj["DRPID"] > current_drpid:
            return proj
    return None


def get_project_by_drpid(drpid: int) -> Optional[Dict[str, Any]]:
    """
    Return the project record for the given DRPID, or None.

    Args:
        drpid: Project identifier.

    Returns:
        Project dict or None.
    """
    _ensure_storage()
    from storage import Storage
    return Storage.get(drpid)


def ensure_output_folder(drpid: int, *, recreate: bool = False) -> Optional[str]:
    """
    Create or resolve the output folder for this DRPID; store in result state.

    By default (``recreate=False``), reuses Storage ``folder_path`` or the
  default ``DRP######`` directory under ``base_output_dir`` without deleting files.
    Only ``/api/projects/load`` passes ``recreate=True`` when the user opts to
    delete the folder on load.

    Args:
        drpid: Project identifier.
        recreate: When True, empty the folder before use.

    Returns:
        folder_path string or None if creation failed.
    """
    import shutil

    from utils.file_utils import create_output_folder

    result = get_result_by_drpid()
    if recreate:
        result.pop(drpid, None)

    _ensure_storage()
    from storage import Storage

    record = Storage.get(drpid) or {}
    stored = (record.get("folder_path") or "").strip()

    if stored:
        folder_path = Path(stored)
        if not recreate and folder_path.is_dir():
            path_str = str(folder_path)
            result[drpid] = {"folder_path": path_str}
            return path_str
        if recreate and folder_path.exists():
            try:
                shutil.rmtree(folder_path)
            except OSError:
                return None
        try:
            folder_path.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
        path_str = str(folder_path)
        result[drpid] = {"folder_path": path_str}
        return path_str

    base_path = get_base_output_dir()
    folder_path = create_output_folder(base_path, drpid, recreate=recreate)
    if not folder_path:
        return None
    path_str = str(folder_path)
    result[drpid] = {"folder_path": path_str}
    return path_str


def add_project_with_source_url(source_url: str) -> Dict[str, Any]:
    """
    Insert a new project with the given source_url and set status to sourced.

    Matches sourcing outcomes so the row is eligible for Next / first load.

    Args:
        source_url: HTTP or HTTPS URL (trimmed).

    Returns:
        Dict with DRPID and source_url.

    Raises:
        ValueError: If URL is missing or invalid, or source_url is already in the DB.
    """
    url = (source_url or "").strip()
    if not url or not is_valid_url(url):
        raise ValueError("valid source_url is required")

    _ensure_storage()
    from storage import Storage

    try:
        drpid = Storage.create_record(url)
    except sqlite3.IntegrityError as e:
        raise ValueError("duplicate_source_url") from e

    Storage.update_record(drpid, {"status": "sourced"})
    rec = Storage.get(drpid) or {}
    stored_url = (rec.get("source_url") or url).strip()
    return {"DRPID": drpid, "source_url": stored_url}


def folder_path_for_drpid(display_drpid: Optional[str]) -> Optional[str]:
    """
    Return folder_path from result state for the given display_drpid.

    Args:
        display_drpid: DRPID as string (may be None).

    Returns:
        folder_path or None.
    """
    if not display_drpid:
        return None
    try:
        drpid = int(display_drpid)
        return get_result_by_drpid().get(drpid, {}).get("folder_path")
    except (ValueError, TypeError):
        return None
