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


def access_outcome_message(
    failed_count: int,
    total_count: int,
    *,
    subject: str = "download file(s)",
    reason: str = "404/access denied",
) -> str | None:
    """
    Build an error that states failures and whether any files succeeded.

    Args:
        failed_count: Number of files that could not be accessed/saved.
        total_count: Total files in the same attempt group.
        subject: Noun phrase for the file group (e.g. ``download file(s)``).
        reason: Short cause label inside parentheses.
    """
    if failed_count <= 0 or total_count <= 0:
        return None
    succeeded = max(total_count - failed_count, 0)
    if failed_count >= total_count:
        return (
            f"All {failed_count} {subject} inaccessible ({reason}); "
            f"none were successfully accessed"
        )
    return (
        f"{failed_count} of {total_count} {subject} inaccessible ({reason}); "
        f"{succeeded} were successfully accessed"
    )


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
    return access_outcome_message(
        len(inaccessible),
        total_files,
        subject="download file(s)",
        reason="404/access denied",
    )
