"""
Shared in-memory state for the Interactive Collector.

Holds the scoreboard (list of visited URLs with status) and per-DRPID results
(folder_path, downloads). Used by both the legacy Flask app and the JSON API.

State is process-local; it does not persist across server restarts.
"""

from pathlib import Path
from typing import Any, Dict, List

# Default paths when not set by orchestrator (standalone run).
DEFAULT_DB_PATH = "drp_pipeline.db"
DEFAULT_BASE_OUTPUT_DIR = r"C:\Documents\DataRescue\DRPData"

# In-memory scoreboard: list of {url, referrer, status_label, is_dupe, ...}.
# Referrer None = root (source) URL.
_scoreboard: List[Dict[str, Any]] = []

# Per-DRPID result: folder_path, downloads list, dataset_size for Save.
_result_by_drpid: Dict[int, Dict[str, Any]] = {}

# One-time metadata from Copy & Open page (title, summary, keywords, agency, office, etc.), keyed by drpid.
_metadata_from_page: Dict[int, Dict[str, str]] = {}


def get_scoreboard() -> List[Dict[str, Any]]:
    """Return the in-memory scoreboard list."""
    return _scoreboard


def get_result_by_drpid() -> Dict[int, Dict[str, Any]]:
    """Return the per-DRPID result dict."""
    return _result_by_drpid


def get_metadata_from_page(drpid: int) -> Dict[str, str]:
    """Return and clear stored metadata-from-page for this drpid (one-time)."""
    return _metadata_from_page.pop(drpid, {})


def set_metadata_from_page(drpid: int, data: Dict[str, str]) -> None:
    """Store metadata extracted from the Copy & Open page (only for that page, not subsequent navigations)."""
    if not data:
        return
    cleaned = {k: (v or "").strip() for k, v in data.items() if v and str(v).strip()}
    if cleaned:
        _metadata_from_page[drpid] = cleaned


def get_db_path() -> Path:
    """Return DB path from Args (when pipeline has initialized it) or default."""
    try:
        from utils.Args import Args
        if getattr(Args, "_initialized", False):
            return Path(Args.db_path)
    except Exception:
        pass
    return Path(DEFAULT_DB_PATH)


def get_base_output_dir() -> Path:
    """Return base output dir from Args (when pipeline has initialized it) or default."""
    try:
        from utils.Args import Args
        if getattr(Args, "_initialized", False):
            return Path(Args.base_output_dir)
    except Exception:
        pass
    return Path(DEFAULT_BASE_OUTPUT_DIR)
