"""
Shared error/warning reporting for DRP Pipeline.

Modules report problems here:
- A "crash" is a fatal problem that stops the entire run.
- An "error" aborts the current project but the pipeline continues with the next.
- A "warning" is non-fatal; processing of the current project continues.
"""

from __future__ import annotations

from typing import NoReturn

from storage import Storage
from utils.ErrorRecord import executing_module, format_project_error
from utils.Logger import Logger


class PipelineFatal(BaseException):
    """Unrecoverable failure. Stops the current batch."""


class ProjectAbort(Exception):
    """The current project was recorded with ``record_error``. The batch continues."""


def normalize_status_hyphens(status: str) -> str:
    """
    Collapse whitespace and spaced hyphens into a compact hyphenated status.

    Example: ``uploaded - large file`` -> ``uploaded-large-file``.
    """
    collapsed = " ".join(str(status).split())
    return collapsed.replace(" - ", "-").replace(" ", "-")


def is_error_status(status: str | None) -> bool:
    """
    Return True when ``status`` is a bare or derived error status.

    Accepts both compact (``sourced-error``) and spaced (``sourced - error``)
    forms; the latter are treated as already-error for idempotent updates.
    """
    if not status or not str(status).strip():
        return False
    normalized = normalize_status_hyphens(status.strip())
    return normalized == "error" or normalized.endswith("-error")


def derive_error_status(previous_status: str | None) -> str:
    """
    Build status after an error from the status the project had when work started.

    Always returns a compact ``xxx-error`` form (no spaces around hyphens).
    Example: ``sourced`` -> ``sourced-error``;
    ``uploaded - large file`` -> ``uploaded-large-file-error``.
    Already-error statuses are returned in normalized form.
    """
    if not previous_status or not str(previous_status).strip():
        return "error"
    prev = normalize_status_hyphens(str(previous_status).strip())
    if prev == "error" or prev.endswith("-error"):
        return prev
    return f"{prev}-error"


def record_crash(msg: str) -> NoReturn:
    """
    Record a crash: log at exception level and raise so the run stops.

    Use for unrecoverable failures (e.g. DB connection lost, config missing).

    Args:
        msg: Crash message to log and raise.

    Raises:
        PipelineFatal: Always, with the given message. Not caught as a project error.
    """
    Logger.exception(msg)
    raise PipelineFatal(msg)


def record_error(
    drpid: int,
    error_msg: str,
    *,
    update_storage: bool = True,
    status_value: str | None = None,
    module: str | None = None,
) -> None:
    """
    Record an error for the current project: abort this project, continue with the next.

    Logs the message, then optionally sets project status and appends a
    structured block to the ``errors`` field so the project is skipped in
    later steps. The first line is an unlabeled summary of the failure.
    The following lines are name:value pairs for drpid, datalumos_id,
    timestamp, module, and details.

    Use ``update_storage=False`` when the record may not exist (e.g. DRPID not found).

    Args:
        drpid: Project DRPID.
        error_msg: Error message to log. Stored as details. The first stored
            line summarizes that text, skipping a generic "failed" prefix and
            bare project ids.
        update_storage: If True, update Storage status and append to errors field.
        status_value: Value for ``status``; default is ``{previous_status}-error``
            in compact form (spaces around hyphens removed). Custom values that
            look like error statuses are also normalized to ``xxx-error``.
        module: Module or script name. Default is the running pipeline module,
            or the caller's file name when that is not set.
    """
    Logger.error(error_msg)

    if not update_storage:
        return

    record = Storage.get(drpid)
    status_value = _status_after_error(record, status_value)
    stored = _stored_error(drpid, error_msg, record, module)

    try:
        Storage.update_record(drpid, {"status": status_value})
        Storage.append_to_field(drpid, "errors", stored)
    except Exception as exc:  # pragma: no cover (defensive; Storage impl may vary)
        Logger.exception(f"Failed recording error for DRPID={drpid}: {exc}")


def _status_after_error(record: dict | None, status_value: str | None) -> str:
    """
    Choose the compact error status to store.

    Args:
        record: Current project row, if it exists.
        status_value: Caller override, or None to derive from the current status.

    Returns:
        Status string to write.
    """
    if status_value is None:
        previous = record.get("status") if record else None
        return derive_error_status(previous)
    if is_error_status(status_value):
        return derive_error_status(status_value)
    return status_value


def _stored_error(
    drpid: int,
    error_msg: str,
    record: dict | None,
    module: str | None,
) -> str:
    """
    Build the structured errors-column block for this failure.

    Args:
        drpid: Project id.
        error_msg: Message to store as details.
        record: Current project row, used for datalumos_id.
        module: Optional module or script name.

    Returns:
        The name:value block appended to errors.
    """
    from storage.StorageSQLLite import local_timestamp

    return format_project_error(
        error_msg,
        drpid,
        _datalumos_id(record),
        executing_module(module),
        local_timestamp(),
    )


def _datalumos_id(record: dict | None) -> str:
    """Return the project's datalumos id, or an empty string when unset."""
    if not record:
        return ""
    raw = record.get("datalumos_id")
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        return ""
    return str(raw).strip()


def abort_project(
    drpid: int,
    error_msg: str,
    *,
    update_storage: bool = True,
) -> NoReturn:
    """
    Record an error and stop further work on this project.

    The batch continues with the next project. Callers that catch ``Exception``
    must let ``ProjectAbort`` through, or catch it and return without recording
    a second error.

    Args:
        drpid: Project DRPID.
        error_msg: Error message to log and persist.
        update_storage: If True, update Storage status and append to errors field.

    Raises:
        ProjectAbort: Always, after the error is recorded.
    """
    record_error(drpid, error_msg, update_storage=update_storage)
    raise ProjectAbort(error_msg)


def record_warning(
    drpid: int,
    warning_msg: str,
    *,
    update_storage: bool = True,
) -> None:
    """
    Record a warning for the current project: non-fatal, processing continues.

    Logs the message, then optionally appends to the project's ``warnings`` field.

    Use ``update_storage=False`` when the record may not exist.

    Args:
        drpid: Project DRPID.
        warning_msg: Warning message to log and persist.
        update_storage: If True, append to Storage warnings field.
    """
    Logger.warning(warning_msg)

    if not update_storage:
        return

    try:
        Storage.append_to_field(drpid, "warnings", warning_msg)
    except Exception as exc:  # pragma: no cover (defensive; Storage impl may vary)
        Logger.exception(f"Failed recording warning for DRPID={drpid}: {exc}")
