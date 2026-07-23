"""
Write Claimed on the inventory Google Sheet when collection completes.

Called by batch collectors (orchestrator) and the interactive collector save path.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from utils.Args import Args
from utils.Logger import Logger


def claim_project_on_inventory_sheet(
    drpid: int,
    project: Optional[Dict[str, Any]] = None,
) -> tuple[bool, Optional[str]]:
    """
    Set Claimed to ``google_username`` for the project's source URL on the sheet tab.

    Skips quietly when sheet credentials are not configured. Logs a warning on
    API failure but does not raise.

    Args:
        drpid: Project DRPID (for log messages).
        project: Optional project dict; when omitted, loaded from Storage.

    Returns:
        (True, None) on success, (False, error_message) on failure or skip.
    """
    sheet_id = (getattr(Args, "google_sheet_id", None) or "").strip()
    creds = getattr(Args, "google_credentials", None)
    if not sheet_id or not creds:
        return False, "Google Sheet not configured"

    if project is None:
        from storage import Storage

        project = Storage.get(drpid)
    if not project:
        return False, f"DRPID {drpid} not found in Storage"

    source_url = (project.get("source_url") or "").strip()
    if not source_url:
        return False, f"DRPID {drpid} has no source_url"

    username = (getattr(Args, "google_username", None) or "").strip()
    if not username:
        return False, "google_username is not set in config"

    from publisher.GoogleSheetUpdater import GoogleSheetUpdater

    updater = GoogleSheetUpdater()
    ok, err = updater.update_claimed(source_url, project=project)
    if ok:
        Logger.info(
            f"Google Sheet Claimed updated for DRPID={drpid} "
            f"(username={username!r})"
        )
    else:
        Logger.warning(
            f"Google Sheet Claimed update failed for DRPID={drpid}: {err}"
        )
    return ok, err


def should_claim_after_collector_status(status: str | None) -> bool:
    """
    Return True when a finished collector run should mark the sheet row claimed.

    Args:
        status: Project status after collection.

    Returns:
        True for successful collected* statuses (not error statuses).
    """
    from utils.Errors import is_error_status

    if is_error_status(status):
        return False
    normalized = (status or "").strip().lower()
    return normalized.startswith("collected")
