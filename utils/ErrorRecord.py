"""
Structured text stored in a project's errors column.

Each recorded failure is one block of name:value lines:

    description: Download failed
    drpid: 12
    datalumos_id: 34567
    timestamp: 2026-10-04 17:49:00
    module: collect
    details: Download failed: report.csv - https://example.com/report.csv
"""

from __future__ import annotations

import inspect
from pathlib import Path

_ERROR_FIELDS: tuple[str, ...] = (
    "description",
    "drpid",
    "datalumos_id",
    "timestamp",
    "module",
    "details",
)
_SKIP_CALLERS = {"Errors.py", "ErrorRecord.py"}
_BRIEF_LIMIT = 120


def single_line(value: object) -> str:
    """
    Collapse whitespace so a field value stays on one line.

    Args:
        value: Text that may contain newlines or extra spaces.

    Returns:
        A single line, or an empty string when value is blank.
    """
    return " ".join(str(value).split())


def brief_error_description(error_msg: str) -> str:
    """
    Take a short label from an error message.

    When the message has a ``: `` and the text before it is non-empty and
    within the brief limit, that prefix is the description. Otherwise the
    whole message is the description.

    Args:
        error_msg: Message passed to ``record_error``.

    Returns:
        One-line description.
    """
    flat = single_line(error_msg)
    head, separator, tail = flat.partition(": ")
    if separator and head and tail and len(head) <= _BRIEF_LIMIT:
        return head
    return flat


def executing_module(explicit: str | None = None) -> str:
    """
    Name the module or script that is recording the error.

    Args:
        explicit: Caller-supplied name. Used as-is when non-empty.

    Returns:
        The pipeline module from Args, or the caller's file name.
    """
    if explicit and explicit.strip():
        return explicit.strip()
    configured = _configured_module()
    if configured:
        return configured
    return _caller_script()


def format_project_error(
    error_msg: str,
    drpid: int,
    datalumos_id: str | None,
    module: str,
    timestamp: str,
) -> str:
    """
    Format one error block for the errors column.

    Args:
        error_msg: Full error message. Stored as details.
        drpid: Project id.
        datalumos_id: DataLumos id, or empty when the project has none.
        module: Module or script that was executing.
        timestamp: Local time the error was recorded.

    Returns:
        Six name:value lines, one field per line.
    """
    values = {
        "description": brief_error_description(error_msg),
        "drpid": str(drpid),
        "datalumos_id": single_line(datalumos_id or ""),
        "timestamp": single_line(timestamp),
        "module": single_line(module),
        "details": single_line(error_msg),
    }
    return "\n".join(_format_line(name, values[name]) for name in _ERROR_FIELDS)


def _format_line(name: str, value: str) -> str:
    """Return ``name: value``, or ``name:`` when value is empty."""
    if value:
        return f"{name}: {value}"
    return f"{name}:"


def _configured_module() -> str | None:
    """Return Args.module when Args is initialized and a module is set."""
    try:
        from utils.Args import Args

        name = Args.module
    except (RuntimeError, AttributeError):
        return None
    if name is None or not str(name).strip():
        return None
    return str(name).strip()


def _caller_script() -> str:
    """Return the file name of the first caller outside this package's helpers."""
    frame = inspect.currentframe()
    try:
        current = frame.f_back if frame is not None else None
        while current is not None:
            filename = current.f_code.co_filename
            if Path(filename).name not in _SKIP_CALLERS:
                return Path(filename).name
            current = current.f_back
    finally:
        del frame
    return "unknown"
