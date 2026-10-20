"""Delete unpublished DataLumos projects, skipping ones that cannot be deleted.

Usage (from the repo root):
  python scripts\\delete_unpublished_projects.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cleanup_inprogress.delete_queue import (
    SKIP_UNDELETABLE_IDS,
    delete_projects,
    deletion_targets,
    load_workspace_ids,
    successful_ids,
)
from cleanup_inprogress.sidebar_project_deleter import SidebarProjectDeleter
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from utils.Args import Args
from utils.Logger import Logger

CSV_PATH = ROOT / "debug" / "unpublished_workspace_projects.csv"
LOG_PATH = ROOT / "debug" / "delete_unpublished_results.csv"


def main() -> int:
    """
    Delete every unpublished project except the undeletable Unpublished ones.

    Returns:
        0 when every attempted delete succeeded, otherwise 1.
    """
    _initialize()
    workspace_ids = load_workspace_ids(CSV_PATH)
    targets = deletion_targets(
        workspace_ids,
        already_deleted=successful_ids(LOG_PATH),
    )
    Logger.info(
        "Skipping undeletable ids %s; deleting %s project(s)",
        ", ".join(SKIP_UNDELETABLE_IDS),
        len(targets),
    )
    session = DataLumosBrowserSession()
    try:
        page = session.ensure_browser()
        session.ensure_authenticated()
        tally = delete_projects(targets, SidebarProjectDeleter(page).delete_one, LOG_PATH)
    finally:
        session.close()
    Logger.info("Finished. %s", tally.summary())
    print(tally.summary())
    return 0 if tally.failure_count == 0 else 1


def _initialize() -> None:
    """Load NPS config and logging without treating this file's argv as a module."""
    sys.argv = ["delete_unpublished_projects", "noop"]
    Args._initialized = False
    Args.initialize()
    Logger.initialize(log_level="INFO")


if __name__ == "__main__":
    raise SystemExit(main())
