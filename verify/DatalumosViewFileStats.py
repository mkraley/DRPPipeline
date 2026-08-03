"""
Extract and compare file statistics from a DataLumos published project view page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.file_utils import format_file_size, parse_file_size_to_bytes

SIZE_TOLERANCE = 0.05
DEFAULT_RECORDS_PER_PAGE = 100
_PAGE_SIZE_SELECTORS = ("#pageSizeOptions", "#recordsPerPage")
_WORKSPACE_PAGER_SELECTOR = "#recordsPerPage"


def _find_page_size_select(page: Page) -> tuple[Optional[str], Optional[object]]:
    """
    Locate the DataLumos ``Records per page`` dropdown on the current page.

    The published view uses ``#pageSizeOptions``; the workspace file manager
    uses ``#recordsPerPage``.

    Args:
        page: Playwright page on a DataLumos project URL.

    Returns:
        ``(selector, element)`` when found, otherwise ``(None, None)``.
    """
    for selector in _PAGE_SIZE_SELECTORS:
        select = page.query_selector(selector)
        if select is not None:
            return selector, select
    return None, None


def wait_for_workspace_file_table(
    page: Page,
    page_size: int = DEFAULT_RECORDS_PER_PAGE,
    timeout: int = 15000,
) -> None:
    """
    Wait for the workspace file table to list all records for the current page size.

    The workspace pager reloads rows via AJAX. ``networkidle`` and
    ``expect_navigation`` are unreliable here; instead wait until the visible
    row count reaches ``min(total records, page_size)``.

    Args:
        page: Playwright page on the DataLumos workspace URL.
        page_size: Selected records-per-page value.
        timeout: Maximum wait in milliseconds.
    """
    try:
        page.wait_for_function(
            """(pageSize) => {
              const rows = document.querySelectorAll('table.table-hover tbody tr').length;
              const match = document.body.innerText.match(/Total of (\\d+) records/);
              if (!match) {
                return rows > 10;
              }
              const total = parseInt(match[1], 10);
              const target = Math.min(total, pageSize);
              return rows >= target;
            }""",
            arg=page_size,
            timeout=timeout,
        )
    except PlaywrightTimeoutError:
        page.wait_for_timeout(1000)


def _wait_after_page_size_change(
    page: Page,
    active_selector: str,
    page_size: int = DEFAULT_RECORDS_PER_PAGE,
) -> None:
    """
    Wait for the file table to reflect a page-size change.

    Args:
        page: Playwright page on a DataLumos project URL.
        active_selector: Selector for the pager control that was changed.
        page_size: Selected records-per-page value.
    """
    if active_selector == _WORKSPACE_PAGER_SELECTOR:
        wait_for_workspace_file_table(page, page_size=page_size)
        return
    page.wait_for_load_state("networkidle", timeout=120000)
    try:
        page.wait_for_selector(active_selector, state="attached", timeout=60000)
    except PlaywrightTimeoutError:
        pass


def set_records_per_page(page: Page, page_size: int = DEFAULT_RECORDS_PER_PAGE) -> bool:
    """
    Set the DataLumos ``Records per page`` dropdown when present.

    The published view uses ``#pageSizeOptions`` and the workspace file manager
    uses ``#recordsPerPage``. Both default to 10 rows. Selecting a larger page
    size (typically 100) ensures projects with more files are fully enumerated.
    Changing the dropdown may trigger ``updatePager`` and a navigation; this
    waits for that update to finish before returning.

    Args:
        page: Playwright page on a DataLumos project or workspace URL.
        page_size: Desired page size option value (default 100).

    Returns:
        True when the dropdown was found and set (or already set); False when absent.
    """
    active_selector, select = _find_page_size_select(page)
    if select is None:
        return False
    desired = str(page_size)
    if select.input_value() == desired:
        return True
    if active_selector == _WORKSPACE_PAGER_SELECTOR:
        select.select_option(desired)
        _wait_after_page_size_change(page, active_selector, page_size)
        return True
    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=120000):
            select.select_option(desired)
    except PlaywrightTimeoutError:
        # Some responses may update without a full document navigation.
        pass
    _wait_after_page_size_change(page, active_selector, page_size)
    return True


_EXTRACT_VIEW_FILES_JS = """
() => {
  const bodyText = (document.body && document.body.innerText) || '';
  if (/just a moment/i.test(bodyText) || /just a minute/i.test(bodyText)) {
    return { error: 'cloudflare_challenge' };
  }
  if (/404|page not found|not found/i.test(document.title + ' ' + bodyText.slice(0, 800))) {
    return { error: 'page_not_found' };
  }
  if (bodyText.includes('File not available for download')) {
    return { error: 'file_not_available' };
  }

  const tables = Array.from(document.querySelectorAll('table'));
  for (const table of tables) {
    const headerCells = Array.from(table.querySelectorAll('thead th, thead td'));
    const headerTexts = headerCells.map(
      h => (h.innerText || '').trim().toLowerCase()
    );
    let nameCol = headerTexts.findIndex(t => /^name\\b/.test(t));
    let sizeCol = headerTexts.findIndex(t => /^size\\b/.test(t));
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    if (rows.length === 0) {
      continue;
    }
    if (nameCol < 0 || sizeCol < 0) {
      const firstTds = rows[0].querySelectorAll('td');
      if (firstTds.length >= 4) {
        nameCol = 1;
        sizeCol = 3;
      } else if (firstTds.length >= 3) {
        nameCol = 0;
        sizeCol = 2;
      } else {
        continue;
      }
    }
    const files = [];
    for (const tr of rows) {
      const tds = Array.from(tr.querySelectorAll('td'));
      if (tds.length === 0) {
        continue;
      }
      const name = (tds[nameCol].innerText || '').trim();
      if (!name) {
        continue;
      }
      const sizeText =
        sizeCol >= 0 && sizeCol < tds.length
          ? (tds[sizeCol].innerText || '').trim()
          : '';
      files.push({ name, size: sizeText });
    }
    if (files.length > 0) {
      return { files };
    }
  }
  return { error: 'no_files_found' };
}
"""


@dataclass(frozen=True)
class DatalumosViewFileStats:
    """File count, names, and total bytes from a DataLumos view page."""

    file_count: int = 0
    total_bytes: int = 0
    file_names: Tuple[str, ...] = ()
    error: Optional[str] = None

    @classmethod
    def from_page(cls, page: Page) -> "DatalumosViewFileStats":
        """
        Evaluate the view page DOM and return parsed file statistics.

        Args:
            page: Playwright page positioned on a DataLumos project view URL.

        Returns:
            Parsed stats, or an instance with ``error`` set on failure.
        """
        raw = _evaluate_view_files(page)
        if not isinstance(raw, dict):
            return cls(error="invalid_page_response")
        if raw.get("error"):
            return cls(error=str(raw["error"]))
        files = raw.get("files")
        if not isinstance(files, list) or not files:
            return cls(error="no_files_found")
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
            return cls(error="no_files_found")
        name_tuple = tuple(names)
        total = sum_sizes_text(sizes)
        if total is None:
            return cls(
                file_count=len(sizes),
                file_names=name_tuple,
                error="unparseable_file_sizes",
            )
        return cls(
            file_count=len(sizes),
            total_bytes=total,
            file_names=name_tuple,
        )


def _evaluate_view_files(page: Page) -> object:
    """
    Run the file-table extractor, retrying once after a mid-navigation race.

    Args:
        page: Playwright page on the DataLumos view URL.

    Returns:
        The value returned by ``page.evaluate``.
    """
    try:
        return page.evaluate(_EXTRACT_VIEW_FILES_JS)
    except Exception as exc:
        message = str(exc)
        if "Execution context was destroyed" not in message and "navigation" not in message.lower():
            raise
        page.wait_for_load_state("domcontentloaded", timeout=120000)
        page.wait_for_load_state("networkidle", timeout=120000)
        return page.evaluate(_EXTRACT_VIEW_FILES_JS)


def sum_sizes_text(sizes: Sequence[str]) -> Optional[int]:
    """
    Sum human-readable size strings to a byte total.

    Args:
        sizes: Size strings from the DataLumos file table.

    Returns:
        Total bytes, or None if any size could not be parsed.
    """
    total = 0
    for size_text in sizes:
        parsed = parse_file_size_to_bytes(size_text)
        if parsed is None:
            return None
        total += parsed
    return total


def sizes_within_tolerance(expected: int, actual: int, tolerance: float = SIZE_TOLERANCE) -> bool:
    """
    Return True when ``actual`` is within ``tolerance`` of ``expected``.

    Args:
        expected: Expected size in bytes.
        actual: Actual size in bytes.
        tolerance: Relative tolerance (default 5%).

    Returns:
        True when the difference is within tolerance.
    """
    if expected < 0 or actual < 0:
        return False
    if expected == 0:
        return actual == 0
    return abs(actual - expected) / expected <= tolerance


def verify_upload_counts(
    db_num_files: Optional[int],
    db_file_size: Optional[str],
    page_stats: DatalumosViewFileStats,
) -> List[str]:
    """
    Compare database inventory fields to DataLumos page statistics.

    Args:
        db_num_files: Expected file count from Storage.
        db_file_size: Expected total size from Storage.
        page_stats: Stats extracted from the DataLumos view page.

    Returns:
        Human-readable error messages; empty when everything matches.
    """
    errors: List[str] = []
    if page_stats.error:
        errors.append(f"DataLumos page error: {page_stats.error}")
        return errors
    if db_num_files is None:
        errors.append("missing num_files in database")
    expected_bytes = parse_file_size_to_bytes(db_file_size)
    if expected_bytes is None:
        errors.append("missing or unparseable file_size in database")
    if errors or db_num_files is None or expected_bytes is None:
        return errors

    count_mismatch = page_stats.file_count != db_num_files
    size_mismatch = not sizes_within_tolerance(expected_bytes, page_stats.total_bytes)
    if count_mismatch or size_mismatch:
        errors.append(
            f"inventory mismatch: "
            f"{format_verify_comparison(db_num_files, db_file_size, page_stats)}"
        )
    return errors


def format_verify_comparison(
    db_num_files: Optional[int],
    db_file_size: Optional[str],
    page_stats: DatalumosViewFileStats,
) -> str:
    """
    Format expected (database) vs actual (DataLumos) files and size.

    Args:
        db_num_files: Expected file count from Storage.
        db_file_size: Expected total size from Storage.
        page_stats: Stats extracted from the DataLumos view page.

    Returns:
        Compact comparison like ``files=5/6 size=3.0 GB/5.0 GB``
        (database/datalumos).
    """
    expected_files = str(db_num_files) if db_num_files is not None else "?"
    actual_files = str(page_stats.file_count)
    expected_bytes = parse_file_size_to_bytes(db_file_size)
    if expected_bytes is not None:
        expected_size = format_file_size(expected_bytes)
    else:
        expected_size = (db_file_size or "").strip() or "?"
    actual_size = format_file_size(page_stats.total_bytes)
    return f"files={expected_files}/{actual_files} size={expected_size}/{actual_size}"


def format_verify_success_message(
    db_num_files: Optional[int],
    db_file_size: Optional[str],
    page_stats: DatalumosViewFileStats,
) -> str:
    """
    Format a one-line success summary with expected vs actual counts and sizes.

    Args:
        db_num_files: Expected file count from Storage.
        db_file_size: Expected total size from Storage.
        page_stats: Stats extracted from the DataLumos view page.

    Returns:
        Summary string like ``files=5/5 size=185.2 MB/185.2 MB``.
    """
    return format_verify_comparison(db_num_files, db_file_size, page_stats)
