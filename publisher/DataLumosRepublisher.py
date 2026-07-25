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

from playwright.sync_api import Page

from publisher.DataLumosPublisher import VIEW_URL_TEMPLATE, DataLumosPublisher
from storage import Storage
from utils.Logger import Logger

REPUBLISH_VERSION_TITLE = "added missing file"
REPUBLISH_VERSION = "V2"
REPUBLISH_STATUS_NOTE = "Republished"
STATUS_UPDATED_INVENTORY = "updated_inventory"


class DataLumosRepublisher(DataLumosPublisher):
    """
    Republish module for projects with status ``re-uploaded``.

    Implements ModuleProtocol. Reuses the publisher browser session, upload
    readiness checks, terms/conditions, and Google Sheet update path.
    """

    def _pre_publish_abort_label(self) -> str:
        """Return ``republish`` for inventory gate error messages."""
        return "republish"

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
