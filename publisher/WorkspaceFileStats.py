"""
Extract file statistics from the DataLumos project workspace file table.

The workspace manager uses ``table.table-hover`` (name/size columns differ from
the published view scraped by ``verify.DatalumosViewFileStats``). Folder rows are
opened so nested files are included in the inventory count.
"""

from __future__ import annotations

from typing import List, Optional

from playwright.sync_api import Page

from utils.Logger import Logger
from verify.DatalumosViewFileStats import (
    DEFAULT_RECORDS_PER_PAGE,
    DatalumosViewFileStats,
    set_records_per_page,
    sum_sizes_text,
    wait_for_workspace_file_table,
)

_MAX_PAGER_RETRIES = 3
_MAX_FOLDER_DEPTH = 25

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


def _open_workspace_folder(page: Page, name: str) -> None:
    """Click a workspace table row to enter a folder."""
    row = page.locator("table.table-hover tbody tr").filter(has_text=name).first
    row.locator("td").nth(1).click()
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
