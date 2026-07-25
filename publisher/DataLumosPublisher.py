"""
DataLumos publisher module.

Implements ModuleProtocol to publish uploaded projects in DataLumos.
Coordinates browser lifecycle, authentication, and the publish workflow.
Publish flow derived from chiara_upload.py (Selenium) → Playwright.
"""

from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright, TimeoutError as PlaywrightTimeoutError

from storage import Storage
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from utils.Args import Args
from utils.project_utils import get_field
from utils.Errors import record_crash, record_error
from utils.Logger import Logger
from utils.project_folder_cleanup import (
    folder_path_can_be_cleared,
    try_delete_project_folder,
)
from publisher.sheet_only_status import resolve_sheet_only_config
from publisher.WorkspaceFileStats import workspace_file_stats_from_page
from verify.DatalumosViewFileStats import verify_upload_counts


# Published / Download Location URL template (``version`` is V1 on first publish, V2 on republish)
VIEW_URL_TEMPLATE = (
    "https://www.datalumos.org/datalumos/project/{workspace_id}/version/{version}/view"
)
PUBLISHED_URL_TEMPLATE = (
    "https://www.datalumos.org/datalumos/project/{workspace_id}/version/V1/view"
)

FILE_NOT_AVAILABLE_TEXT = "File not available for download"

# DataLumos file table: checkbox | name | type | size | ... (third td = type)
_UPLOAD_READINESS_JS = """
() => {
  const spans = Array.from(document.querySelectorAll('span'));
  if (spans.some(s => (s.innerText || '').includes(%(file_not_available)r))) {
    return 'file_not_available';
  }
  const rows = Array.from(document.querySelectorAll('table.table-hover tbody tr'));
  for (const tr of rows) {
    const tds = tr.querySelectorAll('td');
    if (tds.length >= 3) {
      const third = (tds[2].innerText || '').trim();
      if (!third) {
        return 'empty_third_td';
      }
    }
  }
  return null;
}
""" % {"file_not_available": FILE_NOT_AVAILABLE_TEXT}


class DataLumosPublisher:
    """
    Publisher module that publishes uploaded projects in DataLumos.

    Implements ModuleProtocol.     For each eligible project (status="uploaded"),
    this module: authenticates, navigates to the project, verifies workspace
    file count/size against the database, runs the publish
    workflow (Publish Project → review → Proceed to Publish → dialog →
    Publish Data → Back to Project), and updates Storage with published_url
    and status="published".

    Prerequisites: status="upload" and no errors
    Success status: status="published"; status="updated_inventory" after Google Sheet update (if configured).
    """

    WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"

    def __init__(self) -> None:
        """Initialize the DataLumos publisher. Config from Args."""
        self._session = DataLumosBrowserSession()

    def run(self, drpid: int) -> None:
        """
        Run the publish process for a single project.

        Implements ModuleProtocol. Gets project from Storage. For sheet-only
        statuses (not_found, no_links, skip presets, collector_hold - reason):
        updates Google Sheet only (no browser). For status uploaded: validates
        datalumos_id, authenticates, runs publish flow, then updates sheet.

        Args:
            drpid: The DRPID of the project to publish.
        """
        Logger.info(f"Starting publish for DRPID={drpid}")

        project = Storage.get(drpid)
        if project is None:
            record_error(drpid, f"Project with DRPID={drpid} not found in Storage")
            return

        status = (project.get("status") or "").strip()
        sheet_only = resolve_sheet_only_config(status)
        if sheet_only is not None:
            self._run_sheet_only_update(drpid, project, status, sheet_only)
            return

        workspace_id = get_field(project, "datalumos_id")
        if not workspace_id:
            record_error(drpid, "Missing datalumos_id; project must be uploaded before publish")
            return

        publish_ok = False
        try:
            page = self._session.ensure_browser()
            self._session.ensure_authenticated()

            project_url = self._project_url(workspace_id)
            page.goto(project_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=120000)

            from upload.DataLumosAuthenticator import wait_for_human_verification
            wait_for_human_verification(page, timeout=60000)

            gate_error = self._pre_publish_gate(page, project, drpid)
            if gate_error:
                record_error(drpid, gate_error)
            else:
                upload_issue = self._uploads_incomplete_on_project_page(page)
                if upload_issue:
                    Logger.warning(
                        "Skipping publish for DRPID=%s: uploads incomplete — %s",
                        drpid,
                        upload_issue,
                    )
                else:
                    success, error_message = self._publish_workspace(page, drpid)
                    if not success:
                        record_error(drpid, error_message or "Publish workflow failed")
                    else:
                        published_url = self._published_view_url(workspace_id)
                        Storage.update_record(drpid, {
                            "published_url": published_url,
                            "status": "published",
                        })
                        Logger.info(
                            f"Publish completed for DRPID={drpid}, "
                            f"published_url={published_url}"
                        )
                        publish_ok = True
        except Exception as e:
            record_error(drpid, f"Publish failed: {e}")
            raise
        finally:
            self._session.close()

        if not publish_ok:
            return

        # Sheet update is separate: publish already succeeded; TLS/API failures are warnings only.
        try:
            # Reload so sheet Dataset Size / fields reflect any post-collect updates.
            fresh = Storage.get(drpid) or project
            self._update_google_sheet_if_configured(drpid, fresh, workspace_id)
        except RuntimeError:
            raise
        except Exception as e:
            Logger.warning(
                "Google Sheet update failed for DRPID=%s after successful publish: %s",
                drpid,
                e,
            )
            Storage.append_to_field(
                drpid, "warnings", f"Google Sheet update failed: {e}"
            )

        self._finalize_after_publish(drpid)

    def _pre_publish_abort_label(self) -> str:
        """
        Verb used in inventory gate error messages (``publish`` or ``republish``).

        Returns:
            Short label for log and error text.
        """
        return "publish"

    def _pre_publish_gate(
        self,
        page: Page,
        project: Dict[str, Any],
        drpid: int,
    ) -> Optional[str]:
        """
        Abort publish when workspace inventory does not match the database.

        Compares workspace file count/size to Storage ``num_files`` and
        ``file_size`` before starting the publish click sequence.

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
                "DRPID %s: workspace inventory matches database; proceeding to %s",
                drpid,
                self._pre_publish_abort_label(),
            )
            return None
        return (
            f"Aborting {self._pre_publish_abort_label()}: "
            "workspace file count/size does not match database — "
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
        Hook after browser publish and sheet update attempt.

        Args:
            drpid: Project DRPID.
        """
        return

    def _published_view_url(self, workspace_id: str) -> str:
        """
        Build the public DataLumos view URL stored in ``published_url``.

        Args:
            workspace_id: DataLumos project id.

        Returns:
            View URL for the published version (V1 for first publish).
        """
        return VIEW_URL_TEMPLATE.format(workspace_id=workspace_id, version="V1")

    def _sheet_download_version(self) -> str:
        """
        Version segment used for the Google Sheet Download Location column.

        Returns:
            ``V1`` for first publish; republisher overrides to ``V2``.
        """
        return "V1"

    def _update_sheet_if_configured(
        self,
        drpid: int,
        project: Dict[str, Any],
        update_fn: "Callable[[], tuple[bool, Optional[str]]]",
        success_status: str,
    ) -> None:
        """
        If Google Sheet configured, run update_fn; on success set status to success_status.
        Missing credentials or libraries: record_crash. Other failures: append warning.
        """
        if not Args.google_sheet_id or not Args.google_credentials:
            return

        from pathlib import Path

        cred_path = Path(Args.google_credentials) if isinstance(Args.google_credentials, str) else Args.google_credentials
        if not cred_path.exists():
            record_crash(
                f"Google Sheet update configured but credentials file not found: {cred_path}. "
                "Set google_credentials to a valid path or leave unset to skip sheet update."
            )
            return

        source_url = get_field(project, "source_url")
        if not source_url:
            Logger.warning("Google Sheet update skipped: no source_url")
            return

        try:
            success, error_message = update_fn()
        except Exception as exc:
            success = False
            error_message = str(exc)

        if success:
            Storage.update_record(drpid, {"status": success_status})
            Logger.info(f"Sheet updated for DRPID={drpid}")
            if success_status == "updated_inventory":
                self._delete_project_folder_after_inventory_update(drpid)
        elif error_message:
            msg_lower = error_message.lower()
            if "not installed" in msg_lower:
                record_crash(
                    "Google Sheet update configured but Google Sheets API libraries are not installed. "
                    "Install with: pip install google-api-python-client google-auth google-auth-httplib2 "
                    "or leave google_sheet_id/google_credentials unset to skip sheet update."
                )
            Logger.warning(f"Google Sheet update failed for DRPID={drpid}: {error_message}")
            Storage.append_to_field(
                drpid, "warnings", f"Google Sheet update failed: {error_message}"
            )

    def _run_sheet_only_update(
        self,
        drpid: int,
        project: Dict[str, Any],
        status: str,
        sheet_only: tuple[str, str, str],
    ) -> None:
        """Update Google Sheet only for sheet-only statuses (skips / collector holds)."""
        notes_value, status_value, download_possible = sheet_only
        include_metadata = download_possible == "?"

        from publisher.GoogleSheetUpdater import GoogleSheetUpdater

        updater = GoogleSheetUpdater()

        from publisher.sheet_only_status import should_write_claimed_for_sheet_only

        def _do_update() -> tuple[bool, Optional[str]]:
            return updater.update_for_sheet_only(
                source_url=get_field(project, "source_url"),
                notes_value=notes_value,
                dataset_download_possible=download_possible,
                project=project if include_metadata else None,
                log_suffix=f" ({status})",
                write_claimed=should_write_claimed_for_sheet_only(status),
            )

        self._update_sheet_if_configured(drpid, project, _do_update, status_value)

    def _update_google_sheet_if_configured(
        self, drpid: int, project: Dict[str, Any], workspace_id: str
    ) -> None:
        """
        If Google Sheet ID and credentials are configured, update the sheet
        with publishing results (Claimed, Data Added, Download Location, etc.).
        Missing credentials file or missing Google Sheets libraries: record_crash (fatal).
        Other failures (e.g. API error): append warning and continue. If the source URL
        is not in the sheet, a new row is appended (see `GoogleSheetUpdater`).
        """
        from publisher.GoogleSheetUpdater import GoogleSheetUpdater

        updater = GoogleSheetUpdater()

        def _do_update() -> tuple[bool, Optional[str]]:
            return updater.update(
                source_url=get_field(project, "source_url"),
                workspace_id=workspace_id,
                project=project,
                version=self._sheet_download_version(),
            )

        self._update_sheet_if_configured(drpid, project, _do_update, "updated_inventory")

    def _delete_project_folder_after_inventory_update(self, drpid: int) -> None:
        """
        After a successful sheet update to ``updated_inventory``, delete the
        on-disk project folder and clear ``folder_path`` in Storage.
        """
        project = Storage.get(drpid)
        if project is None:
            return

        status = (project.get("status") or "").strip().lower()
        if status != "updated_inventory":
            Logger.warning(
                "Skipping folder delete for DRPID=%s: status=%r",
                drpid,
                status,
            )
            return

        folder_path_raw = get_field(project, "folder_path")
        if not folder_path_raw or not str(folder_path_raw).strip():
            return

        result = try_delete_project_folder(drpid, folder_path_raw)
        if result.deleted:
            Logger.info(
                "Deleted project folder for DRPID=%s: %s",
                drpid,
                result.folder_path,
            )
        elif folder_path_can_be_cleared(result):
            Logger.info(
                "Project folder already absent for DRPID=%s: %s",
                drpid,
                result.folder_path,
            )
        else:
            Logger.warning(
                "Folder not deleted for DRPID=%s: %s",
                drpid,
                result.message,
            )
            return

        Storage.update_record(drpid, {"folder_path": None})

    def _project_url(self, workspace_id: str) -> str:
        """Build URL for a DataLumos project page."""
        return f"{self.WORKSPACE_URL}?goToLevel=project&goToPath=/datalumos/{workspace_id}#"

    def _wait_for_busy(self, page: Page) -> None:
        """Wait for #busy overlay to disappear (same pattern as upload FormFiller)."""
        busy = page.locator("#busy")
        try:
            if busy.count() > 0:
                busy.first.wait_for(state="hidden", timeout=360000)
                page.wait_for_timeout(500)
        except PlaywrightTimeoutError:
            Logger.warning("Timeout waiting for busy overlay to disappear")

    def _uploads_incomplete_on_project_page(self, page: Page) -> Optional[str]:
        """
        Return a warning message when DataLumos shows incomplete uploads.

        Checks (either triggers skip):
        - a span containing "File not available for download"
        - table.table-hover row with empty third <td>
        """
        try:
            result = page.evaluate(_UPLOAD_READINESS_JS)
        except Exception as exc:
            Logger.warning(
                "Could not check upload readiness on project page: %s",
                exc,
            )
            return None

        if result == "file_not_available":
            return f"span contains '{FILE_NOT_AVAILABLE_TEXT}'"
        if result == "empty_third_td":
            return "table.table-hover has a row with empty third column"
        return None

    def _check_errormsg(self, page: Page) -> Optional[str]:
        """If #errormsg is visible and has text, return that text; else None."""
        err_div = page.locator("#errormsg")
        try:
            if err_div.count() > 0 and err_div.first.is_visible(timeout=1000):
                text = err_div.first.inner_text()
                if text and text.strip():
                    return text.strip()
        except PlaywrightTimeoutError:
            pass
        return None

    def _publish_workspace(self, page: Page, drpid: int) -> tuple[bool, Optional[str]]:
        """
        Execute the publish workflow (from chiara_upload.publish_workspace).
        Retry once after 5 seconds on failure.

        Returns:
            (True, None) on success, (False, error_message) on failure.
        """
        for attempt in range(2):
            if attempt > 0:
                Logger.info("Publish workflow failed, retrying after 5 seconds...")
                page.wait_for_timeout(5000)

            try:
                return self._run_publish_flow_once(page, drpid)
            except Exception as e:
                error_msg = str(e)
                Logger.warning(f"Publish attempt {attempt + 1} failed: {error_msg}")
                if attempt == 1:
                    return False, error_msg
        return False, "Publish workflow failed after retry"

    def _click_publish_entry_button(self, page: Page) -> None:
        """
        Click the workspace button that starts the publish review flow.

        Args:
            page: Playwright page on the DataLumos project workspace.
        """
        publish_btn = page.locator("button.btn-primary:has-text('Publish Project')")
        publish_btn.click()

    def _prepare_review_page(self, page: Page) -> None:
        """
        Optional review-page setup before Proceed to Publish.

        Default is a no-op; republish fills Version Title.

        Args:
            page: Playwright page on the review/publish URL.
        """
        return

    def _run_publish_flow_once(self, page: Page, drpid: int) -> tuple[bool, Optional[str]]:
        """Run the publish flow once (no retry). Raises on failure."""
        timeout_ms = Args.upload_timeout

        # Step 1: Click publish / re-publish entry button
        self._wait_for_busy(page)
        self._click_publish_entry_button(page)

        # Step 2: Wait for review page (URL contains reviewPublish)
        try:
            page.wait_for_url(lambda url: "reviewPublish" in url, timeout=timeout_ms)
            page.wait_for_timeout(1000)
        except PlaywrightTimeoutError:
            err_text = self._check_errormsg(page)
            if err_text:
                raise RuntimeError(f"Error message on page: {err_text}")
            raise RuntimeError("Timeout waiting for review/publish page")

        # Step 2b: Optional review fields (e.g. version title on re-publish)
        self._prepare_review_page(page)

        # Step 3: Click "Proceed to Publish"
        self._wait_for_busy(page)
        proceed_btn = page.locator("button.btn-primary:has-text('Proceed to Publish')")
        proceed_btn.click()
        page.wait_for_timeout(1000)

        # Step 4: Dialog – noDisclosure, sensitiveNo, depositAgree
        self._wait_for_busy(page)
        page.locator("#noDisclosure").click()
        page.wait_for_timeout(500)
        self._wait_for_busy(page)
        page.locator("#sensitiveNo").click()
        page.wait_for_timeout(500)
        self._wait_for_busy(page)
        page.locator("#depositAgree").click()
        page.wait_for_timeout(500)

        # Step 5: Click "Publish Data"
        self._wait_for_busy(page)
        publish_data_btn = page.locator("button.btn-primary:has-text('Publish Data')")
        publish_data_btn.click()
        page.wait_for_timeout(2000)

        # Step 6: Click "Back to Project"
        self._wait_for_busy(page)
        back_btn = page.locator("button.btn-primary:has-text('Back to Project')")
        back_btn.click()
        page.wait_for_timeout(2000)

        # Step 7: Wait until back at workspace (URL has /datalumos/ and not reviewPublish)
        try:
            page.wait_for_url(
                lambda url: "/datalumos/" in url and "reviewPublish" not in url,
                timeout=timeout_ms,
            )
        except PlaywrightTimeoutError:
            err_text = self._check_errormsg(page)
            if err_text:
                raise RuntimeError(f"Error message on page: {err_text}")
            raise RuntimeError("Timeout waiting for return to workspace")

        # Step 8: Final error check
        err_text = self._check_errormsg(page)
        if err_text:
            raise RuntimeError(f"Error message on page: {err_text}")

        return True, None
