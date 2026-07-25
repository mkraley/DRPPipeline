"""
Extract file statistics from the DataLumos project workspace file table.

The workspace manager uses ``table.table-hover`` (name/size columns differ from
the published view scraped by ``verify.DatalumosViewFileStats``).
"""

from __future__ import annotations

from typing import List

from playwright.sync_api import Page

from verify.DatalumosViewFileStats import DatalumosViewFileStats, sum_sizes_text

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
  return { files };
}
"""


def workspace_file_stats_from_page(page: Page) -> DatalumosViewFileStats:
    """
    Extract file count and total bytes from the DataLumos workspace file table.

    Args:
        page: Playwright page on the DataLumos project workspace.

    Returns:
        Parsed stats, or an instance with ``error`` set on failure.
    """
    raw = page.evaluate(_WORKSPACE_FILE_STATS_JS)
    if not isinstance(raw, dict):
        return DatalumosViewFileStats(error="invalid_page_response")
    if raw.get("error"):
        return DatalumosViewFileStats(error=str(raw["error"]))
    files = raw.get("files")
    if not isinstance(files, list) or not files:
        return DatalumosViewFileStats(error="no_files_found")
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
        return DatalumosViewFileStats(error="no_files_found")
    name_tuple = tuple(names)
    total = sum_sizes_text(sizes)
    if total is None:
        return DatalumosViewFileStats(
            file_count=len(sizes),
            file_names=name_tuple,
            error="unparseable_file_sizes",
        )
    return DatalumosViewFileStats(
        file_count=len(sizes),
        total_bytes=total,
        file_names=name_tuple,
    )
