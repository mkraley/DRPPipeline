"""Choose DataLumos projects to delete and append a result log."""

import csv
from collections.abc import Callable, Iterable
from pathlib import Path

from cleanup_inprogress.delete_tally import DeleteTally
from utils.Logger import Logger

SKIP_UNDELETABLE_IDS = ("255551", "255552", "255562", "255566")


def load_workspace_ids(csv_path: Path) -> list[str]:
    """
    Read workspace ids from a CSV with a workspace_id column.

    Args:
        csv_path: UTF-8 CSV written by the sidebar parser.

    Returns:
        Ids in file order. Blank and non-numeric values are omitted.
    """
    ids: list[str] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            workspace_id = (row.get("workspace_id") or "").strip()
            if workspace_id.isdigit():
                ids.append(workspace_id)
    return ids


def successful_ids(log_path: Path) -> set[str]:
    """
    Return ids already logged as success.

    Args:
        log_path: Result CSV. Missing files yield an empty set.

    Returns:
        Workspace ids whose outcome column is success.
    """
    if not log_path.exists():
        return set()
    done: set[str] = set()
    with log_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if (row.get("outcome") or "").strip() == "success":
                workspace_id = (row.get("workspace_id") or "").strip()
                if workspace_id:
                    done.add(workspace_id)
    return done


def deletion_targets(
    workspace_ids: list[str],
    skip_ids: Iterable[str] = SKIP_UNDELETABLE_IDS,
    already_deleted: Iterable[str] = (),
) -> list[str]:
    """
    Return ids to delete, preserving order.

    Args:
        workspace_ids: Candidate ids, usually from the unpublished CSV.
        skip_ids: Ids that cannot be deleted, such as Unpublished state.
        already_deleted: Ids already logged as success on a previous run.

    Returns:
        Ids that are not skipped and not already deleted.
    """
    blocked = set(skip_ids) | set(already_deleted)
    return [workspace_id for workspace_id in workspace_ids if workspace_id not in blocked]


def append_result(log_path: Path, workspace_id: str, outcome: str, detail: str) -> None:
    """
    Append one delete result. Creates the CSV with a header when needed.

    Args:
        log_path: Result CSV path.
        workspace_id: Numeric DataLumos project id.
        outcome: ``success`` or ``failure``.
        detail: Short reason or confirmation text.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not log_path.exists()
    encoding = "utf-8-sig" if new_file else "utf-8"
    with log_path.open("a", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(["workspace_id", "outcome", "detail"])
        writer.writerow([workspace_id, outcome, detail])


def delete_projects(
    workspace_ids: list[str],
    delete_one: Callable[[str], tuple[bool, str]],
    log_path: Path,
) -> DeleteTally:
    """
    Delete projects one after another and log each outcome.

    A failure does not stop the remaining ids.

    Args:
        workspace_ids: Ids to delete, already filtered.
        delete_one: Callable returning ``(ok, detail)`` for one id.
        log_path: CSV that receives one row per attempt.

    Returns:
        Tally of successes and failures.
    """
    tally = DeleteTally()
    total = len(workspace_ids)
    for index, workspace_id in enumerate(workspace_ids, start=1):
        ok, detail = _attempt(delete_one, workspace_id)
        _record(tally, log_path, workspace_id, ok, detail, index, total)
    return tally


def _attempt(
    delete_one: Callable[[str], tuple[bool, str]],
    workspace_id: str,
) -> tuple[bool, str]:
    """Return the delete result, converting unexpected errors into failures."""
    try:
        return delete_one(workspace_id)
    except Exception as exc:
        return False, str(exc)


def _record(
    tally: DeleteTally,
    log_path: Path,
    workspace_id: str,
    ok: bool,
    detail: str,
    index: int,
    total: int,
) -> None:
    """Log one outcome, append it, and print the running tally."""
    if ok:
        tally.record_success(workspace_id)
        Logger.info("Deleted %s (%s/%s)", workspace_id, index, total)
        append_result(log_path, workspace_id, "success", detail)
    else:
        tally.record_failure(workspace_id, detail)
        Logger.error("Failed %s (%s/%s): %s", workspace_id, index, total, detail)
        append_result(log_path, workspace_id, "failure", detail)
    Logger.info("Tally %s", tally.summary())
