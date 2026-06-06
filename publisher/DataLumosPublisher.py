"""
DataLumos publisher module.

Implements ModuleProtocol to publish uploaded projects in DataLumos.
Coordinates browser lifecycle, authentication, and the publish workflow.
Publish flow derived from chiara_upload.py (Selenium) → Playwright.
"""

from typing import Any, Callable, Dict, Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright, TimeoutError as PlaywrightTimeoutError

from storage import Storage
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from utils.Args import Args
from utils.project_utils import get_field
from utils.Errors import record_crash, record_error
from utils.Logger import Logger
from utils.project_folder_cleanup import row_has_no_errors, try_delete_project_folder


# Published project URL template (same as Download Location in chiara_upload update_google_sheet)
PUBLISHED_URL_TEMPLATE = "https://www.datalumos.org/datalumos/project/{workspace_id}/version/V1/view"

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

    Implements ModuleProtocol. For each eligible project (status="uploaded"),
    this module: authenticates, navigates to the project, runs the publish
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

        Implements ModuleProtocol. Gets project from Storage. For status
        not_found or no_links: updates Google Sheet only (no browser). For
        status upload: validates datalumos_id, authenticates, runs publish
        flow, then updates sheet.

        Args:
            drpid: The DRPID of the project to publish.
        """
        Logger.info(f"Starting publish for DRPID={drpid}")

        project = Storage.get(drpid)
        if project is None:
            record_error(drpid, f"Project with DRPID={drpid} not found in Storage")
            return

        status = (project.get("status") or "").strip().lower()
        if status in ("not_found", "no_links"):
            self._run_sheet_only_for_not_found_or_no_links(drpid, project, status)
            return

        workspace_id = get_field(project, "datalumos_id")
        if not workspace_id:
            record_error(drpid, "Missing datalumos_id; project must be uploaded before publish")
            return

        try:
            page = self._session.ensure_browser()
            self._session.ensure_authenticated()

            project_url = self._project_url(workspace_id)
            page.goto(project_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=120000)

            from upload.DataLumosAuthenticator import wait_for_human_verification
            wait_for_human_verification(page, timeout=60000)

            upload_issue = self._uploads_incomplete_on_project_page(page)
            if upload_issue:
                Logger.warning(
                    "Skipping publish for DRPID=%s: uploads incomplete — %s",
                    drpid,
                    upload_issue,
                )
                return

            success, error_message = self._publish_workspace(page, drpid)
            if not success:
                record_error(drpid, error_message or "Publish workflow failed")
                return

            published_url = PUBLISHED_URL_TEMPLATE.format(workspace_id=workspace_id)
            Storage.update_record(drpid, {
                "published_url": published_url,
                "status": "published",
            })
            Logger.info(f"Publish completed for DRPID={drpid}, published_url={published_url}")
        except Exception as e:
            record_error(drpid, f"Publish failed: {e}")
            raise
        finally:
            self._session.close()

        # Sheet update is separate: publish already succeeded; TLS/API failures are warnings only.
        try:
            self._update_google_sheet_if_configured(drpid, project, workspace_id)
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

    def _run_sheet_only_for_not_found_or_no_links(
        self, drpid: int, project: Dict[str, Any], status: str
    ) -> None:
        """Update Google Sheet only for not_found/no_links; set status to updated_not_found or updated_no_links on success."""
        notes_value = "Not found" if status == "not_found" else "No live links"
        status_value = "updated_not_found" if status == "not_found" else "updated_no_links"

        from publisher.GoogleSheetUpdater import GoogleSheetUpdater

        updater = GoogleSheetUpdater()

        def _do_update() -> tuple[bool, Optional[str]]:
            return updater.update_for_not_found_or_no_links(
                source_url=get_field(project, "source_url"),
                notes_value=notes_value,
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
            )

        self._update_sheet_if_configured(drpid, project, _do_update, "updated_inventory")

    def _delete_project_folder_after_inventory_update(self, drpid: int) -> None:
        """
        After a successful sheet update to ``updated_inventory``, delete the
        on-disk project folder when the row has no errors.
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

        if not row_has_no_errors(project.get("errors")):
            Logger.info(
                "Skipping folder delete for DRPID=%s: errors present",
                drpid,
            )
            return

        result = try_delete_project_folder(drpid, get_field(project, "folder_path"))
        if result.deleted:
            Logger.info(
                "Deleted project folder for DRPID=%s: %s",
                drpid,
                result.folder_path,
            )
        else:
            Logger.warning(
                "Folder not deleted for DRPID=%s: %s",
                drpid,
                result.message,
            )

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

    def _run_publish_flow_once(self, page: Page, drpid: int) -> tuple[bool, Optional[str]]:
        """Run the publish flow once (no retry). Raises on failure."""
        timeout_ms = Args.upload_timeout

        # Step 1: Click "Publish Project"
        self._wait_for_busy(page)
        publish_btn = page.locator("button.btn-primary:has-text('Publish Project')")
        publish_btn.click()

        # Step 2: Wait for review page (URL contains reviewPublish)
        try:
            page.wait_for_url(lambda url: "reviewPublish" in url, timeout=timeout_ms)
            page.wait_for_timeout(1000)
        except PlaywrightTimeoutError:
            err_text = self._check_errormsg(page)
            if err_text:
                raise RuntimeError(f"Error message on page: {err_text}")
            raise RuntimeError("Timeout waiting for review/publish page")

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
