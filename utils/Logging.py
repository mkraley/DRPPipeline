"""
Shared logging helpers for DRP Pipeline.

These helpers centralize common patterns used across modules, such as recording
fatal per-project errors into Storage while also emitting logs.
"""

from __future__ import annotations

from storage import Storage
from utils.Logger import Logger


def record_fatal_error(
    drpid: int,
    error_msg: str,
    *,
    update_storage: bool = True,
    status_value: str = "Error",
) -> None:
    """
    Record a fatal error for a project.

    Behavior:
    - Always logs the error message.
    - Optionally updates Storage:
      - sets status to ``status_value``
      - appends ``error_msg`` to the ``errors`` field

    Use ``update_storage=False`` when the record may not exist (e.g. DRPID not found),
    since appending to a non-existent record will fail.

    Args:
        drpid: Project DRPID.
        error_msg: Error message to log and persist.
        update_storage: If True, update Storage status and append to errors field.
        status_value: Value to set for the ``status`` column when updating Storage.
    """
    Logger.error(error_msg)

    if not update_storage:
        return

    try:
        Storage.update_record(drpid, {"status": status_value})
        Storage.append_to_field(drpid, "errors", error_msg)
    except Exception as exc:  # pragma: no cover (defensive; Storage impl may vary)
        Logger.exception(f"Failed recording fatal error for DRPID={drpid}: {exc}")

