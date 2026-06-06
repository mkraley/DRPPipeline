"""
Delete on-disk project folders after successful pipeline completion.

Used by the publisher after ``updated_inventory`` and by
``scripts/cleanup_updated_inventory_folders.py`` for batch cleanup.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class FolderDeleteResult:
    deleted: bool
    folder_path: Optional[Path]
    message: str


def row_has_no_errors(errors: object) -> bool:
    if errors is None:
        return True
    return not str(errors).strip()


def is_deletable_folder(path: Path) -> bool:
    """Reject empty, relative, or dangerously shallow paths."""
    if not path.is_absolute():
        return False
    if len(path.parts) < 3:
        return False
    return True


def folder_size_bytes(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            total += entry.stat().st_size
    return total


def evaluate_project_folder(
    drpid: int,
    folder_path_raw: object,
    *,
    compute_size: bool = False,
) -> FolderDeleteResult:
    """Decide whether a project folder can be deleted; optionally compute size."""
    if not folder_path_raw or not str(folder_path_raw).strip():
        return FolderDeleteResult(False, None, "empty folder_path")

    path = Path(str(folder_path_raw))
    if not is_deletable_folder(path):
        return FolderDeleteResult(False, path, "unsafe or relative path")

    if not path.exists():
        return FolderDeleteResult(False, path, "path does not exist")

    if path.is_file():
        return FolderDeleteResult(False, path, "not a directory")

    if compute_size:
        try:
            folder_size_bytes(path)
        except OSError as exc:
            return FolderDeleteResult(False, path, f"cannot size folder ({exc})")

    return FolderDeleteResult(True, path, "ok")


def try_delete_project_folder(
    drpid: int,
    folder_path_raw: object,
) -> FolderDeleteResult:
    """
    Delete ``folder_path`` when it passes safety checks.

    Returns a result describing whether deletion happened. Failures are
    non-fatal (caller should log and continue).
    """
    decision = evaluate_project_folder(drpid, folder_path_raw)
    if not decision.deleted or decision.folder_path is None:
        return FolderDeleteResult(False, decision.folder_path, decision.message)

    try:
        shutil.rmtree(decision.folder_path)
    except OSError as exc:
        return FolderDeleteResult(False, decision.folder_path, str(exc))

    return FolderDeleteResult(
        True,
        decision.folder_path,
        f"deleted {decision.folder_path}",
    )
