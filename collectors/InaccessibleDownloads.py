"""
Helpers for catalog files that return 404 / access denied on probe.

These must not be treated as unknown size (which forces xlarge). They are
recorded as project errors, with status notes that say whether every file or
only some files are inaccessible.
"""

from __future__ import annotations

from collectors.PlannedFile import PlannedFile

# HTTP statuses treated as inaccessible (not merely size unknown).
INACCESSIBLE_HTTP_STATUSES = frozenset({401, 403, 404, 410})


def access_error_for_status(status_code: int | None) -> str | None:
    """
    Return an access-error label for a probe HTTP status, or None if usable.

    Args:
        status_code: Response status from HEAD/GET probe.
    """
    if status_code is None:
        return None
    if int(status_code) in INACCESSIBLE_HTTP_STATUSES:
        return f"HTTP {int(status_code)}"
    return None


def partition_accessible(
    files: list[PlannedFile],
) -> tuple[list[PlannedFile], list[PlannedFile]]:
    """
    Split planned files into accessible vs inaccessible.

    Args:
        files: Planned catalog downloads.
    """
    accessible = [item for item in files if not item.access_error]
    inaccessible = [item for item in files if item.access_error]
    return accessible, inaccessible


def inaccessible_status_notes(inaccessible: list[PlannedFile]) -> list[str]:
    """
    Build per-file status_notes lines for inaccessible downloads.

    Args:
        inaccessible: Files with ``access_error`` set.
    """
    return [
        (
            f"Inaccessible download ({item.access_error}): "
            f"{item.filename()} - {item.source_url}"
        )
        for item in inaccessible
    ]


def inaccessible_error_message(
    inaccessible: list[PlannedFile],
    total_files: int,
) -> str | None:
    """
    Build a project error distinguishing all vs some inaccessible files.

    Args:
        inaccessible: Files that failed access checks.
        total_files: Total catalog download files for the project.
    """
    count = len(inaccessible)
    if count <= 0:
        return None
    if count >= total_files:
        return (
            f"All {count} download file(s) inaccessible "
            f"(404/access denied)"
        )
    return (
        f"{count} of {total_files} download file(s) inaccessible "
        f"(404/access denied)"
    )
