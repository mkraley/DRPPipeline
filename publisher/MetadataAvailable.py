"""Choose the Baserow Metadata available cell from config and project files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

CHECK_FILES = "check_files"
_NAME_MARKERS = ("metadata", "table_info")
_IGNORED_NAMES = frozenset({"project_metadata.json", "product_metadata.json"})


def metadata_available_cell(setting: Any, folder_path: str | None) -> str:
    """
    Return ``yes`` or ``no`` for the Metadata available column.

    ``check_files`` inspects the project folder. ``true`` writes ``yes`` and
    ``false`` writes ``no``.
    """
    if _is_check_files(setting):
        return "yes" if folder_has_metadata_files(folder_path) else "no"
    if setting:
        return "yes"
    return "no"


def folder_has_metadata_files(folder_path: str | None) -> bool:
    """Return True when a file name contains ``metadata`` or ``table_info``.

    ``project_metadata.json`` and ``product_metadata.json`` are landing-page
    sidecars and do not count.
    """
    raw = str(folder_path or "").strip()
    if not raw:
        return False
    root = Path(raw)
    if not root.is_dir():
        return False
    for path in root.rglob("*"):
        if path.is_file() and _name_marks_metadata(path.name):
            return True
    return False


def _is_check_files(setting: Any) -> bool:
    """Return True when the config value is the ``check_files`` state."""
    return isinstance(setting, str) and setting.strip().casefold() == CHECK_FILES


def _name_marks_metadata(filename: str) -> bool:
    """Return True when a file name contains a metadata or table-info marker."""
    folded = filename.casefold()
    if folded in _IGNORED_NAMES:
        return False
    return any(marker in folded for marker in _NAME_MARKERS)
