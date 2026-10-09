"""
Structured text stored in a project's errors column.

The first line is an unlabeled summary of what went wrong. The rest are
name:value lines:

    report.csv - https://example.com/report.csv
    drpid: 12
    datalumos_id: 34567
    timestamp: 2026-10-04 17:49:00
    module: collect
    details: Download failed: report.csv - https://example.com/report.csv
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

_LABELED_FIELDS: tuple[str, ...] = (
    "drpid",
    "datalumos_id",
    "timestamp",
    "module",
    "details",
)
_WRAPPERS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)^orchestrator\s+module=(?:'[^']+'|\"[^\"]+\"|\S+)\s+"
        r"(?:drpid=\d+\s+)?(?:worker\s+)?exception:\s+"
    ),
    re.compile(r"(?i)^exception\s+during\b.+?\bfor\s+drpid\s+\d+\s*:\s+"),
    re.compile(r"(?i)^.+?\s+failed\s+for\s+drpid\s+\d+\s*:\s+"),
    re.compile(r"(?i)^drpid\s*[=:]?\s*\d+\s*:\s+"),
)
_GENERIC_FAILED = re.compile(
    r"(?i)^(?P<head>[^:=()]{1,60}?)\s+(?:failed|error):\s+"
)
_SPECIFIC_HEAD = re.compile(
    r"(?i)\b(?:not|missing|cannot|can't|could\s+not|invalid|no)\b"
)
_ID_CLAUSE = re.compile(
    r"(?i)\s*(?:\b(?:for|with)\b\s+)?\b(?:drpid|datalumos(?:\s*id)?)\b\s*[=:]?\s*\d+"
)
_ID_ONLY = re.compile(
    r"(?i)^(?:(?:drpid|datalumos(?:\s*id)?)\s*[=:]?\s*)?\d+"
    r"(?:\s+(?:(?:drpid|datalumos(?:\s*id)?)\s*[=:]?\s*)?\d+)*$"
)
_SKIP_CALLERS = {"Errors.py", "ErrorRecord.py"}


def single_line(value: object) -> str:
    """
    Collapse whitespace so a field value stays on one line.

    Args:
        value: Text that may contain newlines or extra spaces.

    Returns:
        A single line, or an empty string when value is blank.
    """
    return " ".join(str(value).split())


def error_summary(error_msg: str) -> str:
    """
    Summarize an error message for the unlabeled first line.

    Drops a generic prefix such as ``Download failed`` or
    ``Exception during collection for DRPID 12``, and drops clauses that are
    only a DRPID or DataLumos id. The remaining text is the summary.

    Args:
        error_msg: Message passed to ``record_error``.

    Returns:
        One line describing what went wrong.
    """
    text = single_line(error_msg)
    summary = _without_id_clauses(_without_generic_wrapper(text))
    if _is_blank_or_ids(summary):
        summary = _without_id_clauses(text)
    if _is_blank_or_ids(summary):
        return text
    return summary


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
        An unlabeled summary line, then one name:value line for each remaining field.
    """
    values = {
        "drpid": str(drpid),
        "datalumos_id": single_line(datalumos_id or ""),
        "timestamp": single_line(timestamp),
        "module": single_line(module),
        "details": single_line(error_msg),
    }
    lines = [error_summary(error_msg)]
    lines.extend(_format_line(name, values[name]) for name in _LABELED_FIELDS)
    return "\n".join(lines)


def _without_generic_wrapper(text: str) -> str:
    """Drop leading boilerplate while a substantive remainder remains."""
    current = text
    for _ in range(4):
        peeled = _peel_once(current)
        if peeled is None or _is_blank_or_ids(peeled):
            return current
        current = peeled
    return current


def _peel_once(text: str) -> str | None:
    """Return text after one generic wrapper, or None when none matches."""
    for pattern in _WRAPPERS:
        match = pattern.match(text)
        if match:
            return text[match.end():].strip()
    failed = _GENERIC_FAILED.match(text)
    if failed and _SPECIFIC_HEAD.search(failed.group("head")) is None:
        return text[failed.end():].strip()
    return None


def _without_id_clauses(text: str) -> str:
    """Remove DRPID and DataLumos id clauses, then collapse whitespace."""
    return single_line(_ID_CLAUSE.sub(" ", text))


def _is_blank_or_ids(text: str) -> bool:
    """Return True when text is empty or only project identifiers."""
    stripped = text.strip()
    return not stripped or _ID_ONLY.match(stripped) is not None


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
