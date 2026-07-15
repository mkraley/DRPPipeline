"""
DataLumos republisher module.

Re-publishes projects after missing files were re-uploaded. Same readiness
checks and terms flow as ``DataLumosPublisher``, but clicks
``Re-Publish Project`` and sets Version Title to ``added missing file``.
Writes ``published_url`` and sheet Download Location to version V2, and
refreshes Dataset Size from Storage ``file_size``.

Before republishing, verifies workspace file count/size against the database.
When finished, sets status ``updated_inventory`` and appends a republished note.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from playwright.sync_api import Page

from publisher.DataLumosPublisher import VIEW_URL_TEMPLATE, DataLumosPublisher
from storage import Storage
from utils.Logger import Logger
from utils.project_utils import get_field
from verify.DatalumosViewFileStats import (
    DatalumosViewFileStats,
    sum_sizes_text,
    verify_upload_counts,
)

REPUBLISH_VERSION_TITLE = "added missing file"
REPUBLISH_VERSION = "V2"
REPUBLISH_STATUS_NOTE = "Republished"
STATUS_UPDATED_INVENTORY = "updated_inventory"

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

    The workspace uses ``table.table-hover`` (not the published-view Name/Size
    table scraped by ``DatalumosViewFileStats.from_page``).

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


class DataLumosRepublisher(DataLumosPublisher):
    """
    Republish module for projects with status ``re-uploaded``.

    Implements ModuleProtocol. Reuses the publisher browser session, upload
    readiness checks, terms/conditions, and Google Sheet update path.
    """

    def _published_view_url(self, workspace_id: str) -> str:
        """
        Build the V2 public view URL after re-publish.

        Args:
            workspace_id: DataLumos project id.

        Returns:
            View URL for version V2.
        """
        return VIEW_URL_TEMPLATE.format(
            workspace_id=workspace_id, version=REPUBLISH_VERSION
        )

    def _sheet_download_version(self) -> str:
        """
        Version segment for Google Sheet Download Location after re-publish.

        Returns:
            ``V2``.
        """
        return REPUBLISH_VERSION

    def _pre_publish_gate(
        self,
        page: Page,
        project: Dict[str, Any],
        drpid: int,
    ) -> Optional[str]:
        """
        Abort republish when workspace inventory does not match the database.

        Args:
            page: Playwright page on the DataLumos project workspace.
            project: Storage project record.
            drpid: Project DRPID.

        Returns:
            Combined error message when mismatched; None when inventory matches.
        """
        errors = self._workspace_inventory_mismatches(page, project)
        if not errors:
            Logger.info(
                "DRPID %s: workspace inventory matches database; proceeding to republish",
                drpid,
            )
            return None
        # Return message for DataLumosPublisher.run to persist via record_error
        # (do not Logger.error here — that skips Storage status/errors).
        return (
            "Aborting republish: workspace file count/size does not match database — "
            + "; ".join(errors)
        )

    def _workspace_inventory_mismatches(
        self,
        page: Page,
        project: Dict[str, Any],
    ) -> List[str]:
        """
        Compare workspace file count/size to Storage ``num_files`` / ``file_size``.

        Args:
            page: Playwright page on the DataLumos project workspace.
            project: Storage project record.

        Returns:
            Human-readable mismatch messages; empty when inventory matches.
        """
        page_stats = workspace_file_stats_from_page(page)
        db_num_files = project.get("num_files")
        if db_num_files is not None:
            db_num_files = int(db_num_files)
        db_file_size = get_field(project, "file_size")
        return verify_upload_counts(db_num_files, db_file_size, page_stats)

    def _finalize_after_publish(self, drpid: int) -> None:
        """
        Set ``updated_inventory`` and append a republished status note.

        Args:
            drpid: Project DRPID.
        """
        Storage.update_record(drpid, {"status": STATUS_UPDATED_INVENTORY})
        self._append_status_note(drpid, REPUBLISH_STATUS_NOTE)
        Logger.info(
            "DRPID %s: republish complete; status=%s note=%r",
            drpid,
            STATUS_UPDATED_INVENTORY,
            REPUBLISH_STATUS_NOTE,
        )

    def _append_status_note(self, drpid: int, note: str) -> None:
        """
        Append a line to ``status_notes`` without duplicating an identical note.

        Args:
            drpid: Project DRPID.
            note: Note text to append.
        """
        project = Storage.get(drpid) or {}
        existing = (project.get("status_notes") or "").strip()
        if note in existing.splitlines():
            return
        new_value = f"{existing}\n{note}".strip() if existing else note
        Storage.update_record(drpid, {"status_notes": new_value})

    def _click_publish_entry_button(self, page: Page) -> None:
        """
        Click ``Re-Publish Project`` on the workspace page.

        Args:
            page: Playwright page on the DataLumos project workspace.
        """
        republish_btn = page.locator(
            "button.btn-primary:has-text('Re-Publish Project')"
        )
        republish_btn.click()

    def _prepare_review_page(self, page: Page) -> None:
        """
        Fill Version Title on the re-publish review page.

        Args:
            page: Playwright page on the review/publish URL.
        """
        self._wait_for_busy(page)
        version_input = page.locator("#versionTitle")
        version_input.wait_for(state="visible", timeout=60000)
        version_input.fill(REPUBLISH_VERSION_TITLE)
        Logger.info(
            "Set re-publish Version Title to %r",
            REPUBLISH_VERSION_TITLE,
        )
