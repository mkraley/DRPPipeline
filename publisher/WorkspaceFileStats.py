"""
Extract file statistics from the DataLumos project workspace file table.

The workspace manager uses ``table.table-hover`` (name/size columns differ from
the published view scraped by ``verify.DatalumosViewFileStats``).
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
    const size = (tds[3].innerText || '').trim();
    files.push({ name, size });
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
    """
    Run the workspace file-table extractor, retrying once after a navigation race.

    Args:
        page: Playwright page on the DataLumos workspace URL.

    Returns:
        The value returned by ``page.evaluate``.
    """
    try:
        return page.evaluate(_WORKSPACE_FILE_STATS_JS)
    except Exception as exc:
        message = str(exc)
        if "Execution context was destroyed" not in message and "navigation" not in message.lower():
            raise
        page.wait_for_load_state("domcontentloaded", timeout=120000)
        wait_for_workspace_file_table(page)
        return page.evaluate(_WORKSPACE_FILE_STATS_JS)


def _parse_workspace_payload(
    raw: object,
) -> tuple[Optional[DatalumosViewFileStats], Optional[int], int]:
    """
    Parse the workspace evaluate payload into stats or an incomplete count.

    Returns:
        ``(stats_or_none, total_records, visible_count)``. When ``stats_or_none``
        is set, parsing finished (success or hard error). When it is None, the
        visible row count is still short of ``total_records``.
    """
    if not isinstance(raw, dict):
        return DatalumosViewFileStats(error="invalid_page_response"), None, 0
    if raw.get("error"):
        return DatalumosViewFileStats(error=str(raw["error"])), None, 0
    files = raw.get("files")
    if not isinstance(files, list) or not files:
        return DatalumosViewFileStats(error="no_files_found"), None, 0

    names: List[str] = []
    sizes: List[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        names.append(name)
        sizes.append(str(entry.get("size") or "").strip())
    if not sizes:
        return DatalumosViewFileStats(error="no_files_found"), None, 0

    total_records_raw = raw.get("totalRecords")
    total_records: Optional[int] = None
    if isinstance(total_records_raw, int) and total_records_raw > 0:
        total_records = total_records_raw
    elif isinstance(total_records_raw, str) and total_records_raw.isdigit():
        total_records = int(total_records_raw)

    visible = len(sizes)
    if total_records is not None and visible < total_records:
        return None, total_records, visible

    name_tuple = tuple(names)
    total = sum_sizes_text(sizes)
    if total is None:
        return (
            DatalumosViewFileStats(
                file_count=visible,
                file_names=name_tuple,
                error="unparseable_file_sizes",
            ),
            total_records,
            visible,
        )
    return (
        DatalumosViewFileStats(
            file_count=visible,
            total_bytes=total,
            file_names=name_tuple,
        ),
        total_records,
        visible,
    )


def workspace_file_stats_from_page(page: Page) -> DatalumosViewFileStats:
    """
    Extract file count and total bytes from the DataLumos workspace file table.

    Raises the records-per-page control above the default of 10 and retries when
    the visible row count is still below the workspace ``Total of N records``.

    Args:
        page: Playwright page on the DataLumos project workspace.

    Returns:
        Parsed stats, or an instance with ``error`` set on failure.
    """
    last_visible = 0
    last_total: Optional[int] = None
    for attempt in range(1, _MAX_PAGER_RETRIES + 1):
        set_records_per_page(page, DEFAULT_RECORDS_PER_PAGE)
        wait_for_workspace_file_table(page, page_size=DEFAULT_RECORDS_PER_PAGE)
        raw = _evaluate_workspace_files(page)
        stats, total_records, visible = _parse_workspace_payload(raw)
        if stats is not None:
            return stats
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

    return DatalumosViewFileStats(
        file_count=last_visible,
        error=(
            f"incomplete_page: visible={last_visible} total={last_total} "
            f"(records-per-page still capped?)"
        ),
    )
