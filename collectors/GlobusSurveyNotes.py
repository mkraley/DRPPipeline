"""Format Globus remote inventory lines for ``status_notes``."""

from __future__ import annotations

import re
from datetime import date

from collectors.GlobusPathInventory import GlobusInventorySummary
from utils.file_utils import format_file_size

SURVEY_LINE_PREFIX = "Globus remote inventory:"
_SURVEY_LINE = re.compile(
    rf"^{re.escape(SURVEY_LINE_PREFIX)}.*$",
    re.MULTILINE,
)


def has_survey_notes(status_notes: str | None) -> bool:
    """
    Return True when ``status_notes`` already contains a survey line.

    Args:
        status_notes: Existing storage status_notes text.

    Returns:
        True if a Globus inventory line is present.
    """
    if not status_notes:
        return False
    return SURVEY_LINE_PREFIX in status_notes


def format_survey_line(summary: GlobusInventorySummary, survey_date: str | None = None) -> str:
    """
    Build a single-line Globus inventory summary for ``status_notes``.

    Args:
        summary: Remote inventory totals.
        survey_date: ISO date string; defaults to today.

    Returns:
        Human-readable inventory line.
    """
    when = survey_date or date.today().isoformat()
    size_text = format_file_size(summary.total_bytes)
    return (
        f"{SURVEY_LINE_PREFIX} {summary.file_count:,} files in "
        f"{summary.dir_count:,} dirs, {size_text} "
        f"(surveyed {when}, path {summary.root_path})"
    )


def upsert_survey_line(
    status_notes: str | None,
    summary: GlobusInventorySummary,
    *,
    survey_date: str | None = None,
) -> str:
    """
    Append or replace the Globus inventory line in ``status_notes``.

    Args:
        status_notes: Existing notes text.
        summary: Remote inventory totals.
        survey_date: ISO date string; defaults to today.

    Returns:
        Updated status_notes preserving the external URL and other lines.
    """
    line = format_survey_line(summary, survey_date=survey_date)
    if not status_notes or not status_notes.strip():
        return line
    if _SURVEY_LINE.search(status_notes):
        return _SURVEY_LINE.sub(line, status_notes).strip()
    return f"{status_notes.strip()}\n{line}"
