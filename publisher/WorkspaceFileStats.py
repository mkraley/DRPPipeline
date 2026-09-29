"""
Extract file statistics from the DataLumos project workspace.

Publish inventory uses the Storage Status panel (space used and file/folder
count) instead of opening every folder in the file table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.Logger import Logger
from utils.file_utils import parse_file_size_to_bytes
from verify.DatalumosViewFileStats import (
    DEFAULT_RECORDS_PER_PAGE,
    DatalumosViewFileStats,
    set_records_per_page,
    sizes_within_tolerance,
    sum_sizes_text,
    wait_for_workspace_file_table,
)

_MAX_PAGER_RETRIES = 3
_MAX_FOLDER_DEPTH = 25

_STORAGE_STATUS_JS = """
() => {
  const rows = Array.from(document.querySelectorAll('div.row'));
  let space = '';
  let fileFolder = '';
  for (const row of rows) {
    const strong = row.querySelector('strong');
    const label = strong ? (strong.innerText || '').trim() : '';
    const value = row.querySelector('sup span');
    const text = value ? (value.innerText || '').trim() : '';
    if (label.startsWith('Space')) space = text;
    if (label.startsWith('File/Folder')) fileFolder = text;
  }
  if (!space && !fileFolder) return { error: 'storage_status_not_found' };
  return { space, fileFolder };
}
"""

# Workspace file manager: checkbox | name | type | size | lastModified | actions
_WORKSPACE_FILE_STATS_JS = """
() => {
  const rows = Array.from(document.querySelectorAll('table.table-hover tbody tr'));
  if (rows.length === 0) {
    return { error: 'no_files_found' };
  }
  const files = [];
  for (const tr of rows) {
    const tds = Array.from(tr.querySelectorAll('td'));
    if (tds.length < 4) {
      continue;
    }
    const name = (tds[1].innerText || '').trim();
    if (!name) {
      continue;
    }
    const type = (tds[2].innerText || '').trim();
    const size = (tds[3].innerText || '').trim();
    const isFolder = !!tr.querySelector('i.glyphicon-folder-open');
    files.push({ name, type, size, isFolder });
  }
  if (files.length === 0) {
    return { error: 'no_files_found' };
  }
  const match = document.body.innerText.match(/Total of (\\d+) records/);
  const totalRecords = match ? parseInt(match[1], 10) : null;
  return { files, totalRecords };
}
"""


@dataclass(frozen=True)
class WorkspaceStorageStatus:
    """Space used and file/folder count from the workspace Storage Status panel."""

    space_label: str = ""
    file_folder_count: Optional[int] = None
    error: Optional[str] = None


def workspace_storage_status_from_page(page: Page) -> WorkspaceStorageStatus:
    """Read the Storage Status panel on the current workspace page."""
    try:
        raw = page.evaluate(_STORAGE_STATUS_JS)
    except Exception as exc:
        return WorkspaceStorageStatus(error=f"storage_status_read_failed: {exc}")
    return _parse_storage_status(raw)


def workspace_storage_mismatches(page: Page, project: dict[str, Any]) -> list[str]:
    """
    Compare Storage Status to ``num_files`` plus product folders and ``file_size``.

    Product rows become folders on DataLumos, so the panel File/Folder count is
    ``num_files + product_count``. A space label like ``< 0.01 GB`` matches any
    database size strictly below that threshold.
    """
    status = workspace_storage_status_from_page(page)
    if status.error:
        return [f"DataLumos page error: {status.error}"]
    expected_files = _expected_file_folder_count(project)
    expected_size = str(project.get("file_size") or "").strip()
    errors: list[str] = []
    if expected_files is None:
        errors.append("missing num_files in database")
    if parse_file_size_to_bytes(expected_size) is None:
        errors.append("missing or unparseable file_size in database")
    if errors:
        return errors
    count_mismatch = status.file_folder_count != expected_files
    size_mismatch = not _space_label_matches(expected_size, status.space_label)
    if count_mismatch or size_mismatch:
        actual_files = (
            "?" if status.file_folder_count is None else str(status.file_folder_count)
        )
        errors.append(
            "inventory mismatch: "
            f"files={expected_files}/{actual_files} "
            f"size={expected_size or '?'}/{status.space_label or '?'}"
        )
    return errors


def nps_product_folder_count(drpid: int) -> int:
    """Return how many NPS product folders belong to ``drpid``."""
    try:
        from storage.NpsHierarchyStore import NpsHierarchyStore

        return len(NpsHierarchyStore.from_storage().list_products_for_drpid(drpid))
    except Exception:
        Logger.debug("No NPS product rows for DRPID %s", drpid)
        return 0


def _parse_storage_status(raw: object) -> WorkspaceStorageStatus:
    """Turn the Storage Status evaluate payload into a status object."""
    if not isinstance(raw, dict):
        return WorkspaceStorageStatus(error="invalid_page_response")
    if raw.get("error"):
        return WorkspaceStorageStatus(error=str(raw["error"]))
    space = str(raw.get("space") or "").strip()
    file_text = str(raw.get("fileFolder") or "").strip()
    if not file_text.isdigit():
        return WorkspaceStorageStatus(space_label=space, error="unparseable_file_folder_count")
    return WorkspaceStorageStatus(space_label=space, file_folder_count=int(file_text))


def _expected_file_folder_count(project: dict[str, Any]) -> Optional[int]:
    """Return ``num_files`` plus product folders that DataLumos counts."""
    raw = project.get("num_files")
    if raw is None or raw == "":
        return None
    drpid = project.get("DRPID") or project.get("drpid")
    products = nps_product_folder_count(int(drpid)) if drpid else 0
    return int(raw) + products


def _space_label_matches(db_file_size: str, space_label: str) -> bool:
    """
    Return True when the panel space label agrees with the database size.

    Exact labels use the same 10% or 1 MiB tolerance as the file-table check.
    A rounded label such as ``0.01 GB`` also matches any size within half of
    that displayed step.
    """
    expected = parse_file_size_to_bytes(db_file_size)
    label = (space_label or "").replace("&lt;", "<").strip()
    if expected is None or not label:
        return False
    upper_bound = label.startswith("<")
    numeric = label.lstrip("<").strip()
    limit = parse_file_size_to_bytes(numeric)
    if limit is None:
        return False
    if upper_bound:
        return expected < limit
    if sizes_within_tolerance(expected, limit):
        return True
    half_step = _displayed_half_step_bytes(numeric)
    if half_step is None:
        return False
    return abs(expected - limit) <= half_step


def _displayed_half_step_bytes(numeric_label: str) -> Optional[int]:
    """Return half of the smallest unit shown in a size label, in bytes."""
    match = re.match(r"^(\d+(?:\.(\d+))?)\s*([A-Za-z]+)$", numeric_label.strip())
    if match is None:
        return None
    fraction = match.group(2) or ""
    decimals = len(fraction)
    step = 10 ** (-decimals) if decimals else 1.0
    one_unit = parse_file_size_to_bytes(f"1 {match.group(3)}")
    if one_unit is None:
        return None
    return int(step * one_unit / 2)


def _evaluate_workspace_files(page: Page) -> object:
    """Run the workspace file-table extractor, retrying after a navigation race."""
    try:
        return page.evaluate(_WORKSPACE_FILE_STATS_JS)
    except Exception as exc:
        message = str(exc)
        if "Execution context was destroyed" not in message and "navigation" not in message.lower():
            raise
        page.wait_for_load_state("domcontentloaded", timeout=120000)
        wait_for_workspace_file_table(page)
        return page.evaluate(_WORKSPACE_FILE_STATS_JS)


def _parse_workspace_entries(
    raw: object,
) -> tuple[Optional[list[dict[str, str]]], Optional[str], Optional[int], int]:
    """
    Parse the workspace evaluate payload into row dicts.

    Returns:
        ``(entries, error, total_records, visible_count)``. ``entries`` is None
        when the visible row count is still short of ``total_records``.
    """
    if not isinstance(raw, dict):
        return [], "invalid_page_response", None, 0
    if raw.get("error"):
        return [], str(raw["error"]), None, 0
    files = raw.get("files")
    if not isinstance(files, list) or not files:
        return [], "no_files_found", None, 0
    entries: list[dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        is_folder = item.get("isFolder")
        entries.append(
            {
                "name": name,
                "type": str(item.get("type") or "").strip(),
                "size": str(item.get("size") or "").strip(),
                "isFolder": "true" if is_folder else "",
            }
        )
    if not entries:
        return [], "no_files_found", None, 0
    total_records = _optional_total_records(raw.get("totalRecords"))
    visible = len(entries)
    if total_records is not None and visible < total_records:
        return None, None, total_records, visible
    return entries, None, total_records, visible


def _optional_total_records(raw: object) -> Optional[int]:
    """Parse the workspace ``Total of N records`` value."""
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _entry_is_folder(entry: dict[str, str]) -> bool:
    """Return True when a workspace row is a folder rather than a file."""
    if (entry.get("isFolder") or "").casefold() == "true":
        return True
    return "folder" in (entry.get("type") or "").casefold()


def _wait_for_workspace_busy(page: Page) -> None:
    """Wait until the DataLumos ``#busy`` overlay is gone before clicking a row."""
    busy = page.locator("#busy")
    try:
        if busy.count() == 0:
            return
        busy.first.wait_for(state="hidden", timeout=120000)
    except PlaywrightTimeoutError:
        Logger.warning("Timeout waiting for workspace busy overlay to disappear")


def _click_workspace_folder_row(page: Page, name: str) -> None:
    """
    Click the name cell for ``name``.

    The workspace table re-renders while ``#busy`` is up, which detaches the
    row mid-click. Re-resolve the row after the overlay clears.
    """
    last_error: Exception | None = None
    for _attempt in range(3):
        _wait_for_workspace_busy(page)
        cell = (
            page.locator("table.table-hover tbody tr")
            .filter(has_text=name)
            .first.locator("td")
            .nth(1)
        )
        try:
            cell.click(timeout=20000)
            return
        except PlaywrightTimeoutError as exc:
            last_error = exc
            page.wait_for_timeout(500)
    if last_error is not None:
        raise last_error


def _open_workspace_folder(page: Page, name: str) -> None:
    """Click a workspace table row to enter a folder."""
    _click_workspace_folder_row(page, name)
    page.wait_for_load_state("domcontentloaded", timeout=120000)
    wait_for_workspace_file_table(page)


def _leave_workspace_folder(page: Page) -> None:
    """Return from a workspace folder to its parent listing."""
    page.go_back()
    page.wait_for_load_state("domcontentloaded", timeout=120000)
    wait_for_workspace_file_table(page)


def _workspace_entries_from_page(
    page: Page,
) -> tuple[list[dict[str, str]], Optional[str], int]:
    """Load the current workspace table, retrying when the pager is capped."""
    last_visible = 0
    last_total: Optional[int] = None
    for attempt in range(1, _MAX_PAGER_RETRIES + 1):
        set_records_per_page(page, DEFAULT_RECORDS_PER_PAGE)
        wait_for_workspace_file_table(page, page_size=DEFAULT_RECORDS_PER_PAGE)
        entries, error, total_records, visible = _parse_workspace_entries(
            _evaluate_workspace_files(page)
        )
        if entries is not None:
            return entries, error, visible
        last_visible = visible
        last_total = total_records
        Logger.warning(
            "Workspace file table incomplete (attempt %s/%s): visible=%s total=%s; "
            "retrying records-per-page",
            attempt,
            _MAX_PAGER_RETRIES,
            visible,
            total_records,
        )
        page.wait_for_timeout(1500)
    return [], (
        f"incomplete_page: visible={last_visible} total={last_total} "
        "(records-per-page still capped?)"
    ), last_visible


def workspace_file_stats_from_page(page: Page, *, _depth: int = 0) -> DatalumosViewFileStats:
    """
    Extract file count and total bytes from the workspace file table.

    Folder rows are opened so nested files are counted. Raises records-per-page
    above the default of 10 and retries when the visible row count is still
    below the workspace ``Total of N records``.
    """
    entries, error, visible = _workspace_entries_from_page(page)
    if error:
        return DatalumosViewFileStats(file_count=visible, error=error)
    return _stats_including_folders(page, entries, depth=_depth)


def _stats_including_folders(
    page: Page,
    entries: list[dict[str, str]],
    *,
    depth: int,
) -> DatalumosViewFileStats:
    """Sum files at this level and recurse into folder rows."""
    names: List[str] = []
    sizes: List[str] = []
    folders: List[str] = []
    for entry in entries:
        if _entry_is_folder(entry):
            folders.append(entry["name"])
            continue
        names.append(entry["name"])
        sizes.append(entry["size"])
    total = 0 if not sizes else sum_sizes_text(sizes)
    if sizes and total is None:
        return DatalumosViewFileStats(
            file_count=len(names),
            file_names=tuple(names),
            error="unparseable_file_sizes",
        )
    if depth >= _MAX_FOLDER_DEPTH and folders:
        return DatalumosViewFileStats(error="folder_walk_too_deep")
    count = len(names)
    bytes_total = int(total or 0)
    all_names = list(names)
    for folder_name in folders:
        _open_workspace_folder(page, folder_name)
        nested = workspace_file_stats_from_page(page, _depth=depth + 1)
        _leave_workspace_folder(page)
        if nested.error:
            return nested
        count += nested.file_count
        bytes_total += nested.total_bytes
        all_names.extend(nested.file_names)
    return DatalumosViewFileStats(
        file_count=count,
        total_bytes=bytes_total,
        file_names=tuple(all_names),
    )
