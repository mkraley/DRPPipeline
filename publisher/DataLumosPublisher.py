"""
DataLumos publisher module.

Implements ModuleProtocol to publish uploaded projects in DataLumos.
Coordinates browser lifecycle, authentication, and the publish workflow.
Publish flow derived from chiara_upload.py (Selenium) → Playwright.
"""

import re
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright, TimeoutError as PlaywrightTimeoutError

from storage import Storage
from upload.DataLumosAuthenticator import datalumos_session_error
from upload.DataLumosBrowserSession import DataLumosBrowserSession, sign_in_required
from utils.Args import Args
from utils.project_utils import get_field
from utils.Errors import PipelineFatal, ProjectAbort, record_crash, record_error
from utils.Logger import Logger
from utils.project_folder_cleanup import (
    folder_path_can_be_cleared,
    try_delete_project_folder,
)
from publisher.GWDANominator import GWDANominator
from publisher.PublishTermsDialog import PublishTermsDialog
from publisher.sheet_only_status import resolve_sheet_only_config


# Published / Download Location URL template (``version`` is V1 on first publish, V2 on republish)
VIEW_URL_TEMPLATE = (
    "https://www.datalumos.org/datalumos/project/{workspace_id}/version/{version}/view"
)
PUBLISHED_URL_TEMPLATE = (
    "https://www.datalumos.org/datalumos/project/{workspace_id}/version/V1/view"
)

FILE_NOT_AVAILABLE_TEXT = "File not available for download"

# Workspace file table: checkbox | name | type | size | ...
# Folder rows leave type (and often size) blank; that is not an incomplete upload.
_UPLOAD_READINESS_JS = """
() => {
  const spans = Array.from(document.querySelectorAll('span'));
  if (spans.some(s => (s.innerText || '').includes(%(file_not_available)r))) {
    return { error: 'file_not_available' };
  }
  const rows = Array.from(document.querySelectorAll('table.table-hover tbody tr'));
  return {
    rows: rows.map(tr => {
      const tds = Array.from(tr.querySelectorAll('td'));
      const text = (index) => ((tds[index] && tds[index].innerText) || '').trim();
      return {
        name: text(1),
        type: text(2),
        size: text(3),
        isFolder: !!tr.querySelector('i.glyphicon-folder-open'),
      };
    }),
  };
}
""" % {"file_not_available": FILE_NOT_AVAILABLE_TEXT}

# The goToPath URL shows the workspace list first, then the project page.
_PROJECT_CONTROLS_TIMEOUT_MS = 5 * 60 * 1000

# True when this project page shows Storage Status and a publish button.
_PROJECT_READY_JS = """
(workspaceId) => {
  const url = window.location.href || "";
  const onProject = url.indexOf("/datalumos/" + workspaceId) !== -1
    && url.indexOf("reviewPublish") === -1;
  if (!onProject) return false;
  const rows = Array.from(document.querySelectorAll("div.row"));
  let hasStorage = false;
  for (const row of rows) {
    const strong = row.querySelector("strong");
    const label = strong ? (strong.innerText || "").trim() : "";
    if (label.indexOf("Space") === 0 || label.indexOf("File/Folder") === 0) {
      hasStorage = true;
    }
  }
  const buttons = Array.from(document.querySelectorAll("button.btn-primary"));
  const hasPublish = buttons.some((button) => {
    const text = (button.innerText || "").toLowerCase();
    return text.indexOf("publish project") !== -1;
  });
  return hasStorage && hasPublish;
}
"""


def _workspace_id_from_project_url(project_url: str) -> str:
    """Return the numeric DataLumos id embedded in a workspace URL."""
    match = re.search(r"/datalumos/(\d+)", project_url)
    return match.group(1) if match else ""


def incomplete_upload_reason(result: object) -> Optional[str]:
    """
    Interpret the workspace upload-readiness payload.

    Args:
        result: Evaluate result from ``_UPLOAD_READINESS_JS``.

    Returns:
        A skip reason, or None when uploads look complete.
    """
    if result == "file_not_available" or (
        isinstance(result, dict) and result.get("error") == "file_not_available"
    ):
        return f"span contains '{FILE_NOT_AVAILABLE_TEXT}'"
    if not isinstance(result, dict):
        return None
    rows = result.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict) or _workspace_row_is_folder(row):
            continue
        name = str(row.get("name") or "").strip()
        size = str(row.get("size") or "").strip()
        if name and not size:
            return f"file has no size: {name}"
    return None


def _workspace_row_is_folder(row: dict) -> bool:
    """Return True when a workspace table row is a folder."""
    if row.get("isFolder") is True:
        return True
    return "folder" in str(row.get("type") or "").casefold()


class DataLumosPublisher:
    """
    Publisher module that publishes uploaded projects in DataLumos.

    Implements ModuleProtocol.     For each eligible project (status
    ``uploaded``), this module: nominates the source URL to GWDA, authenticates,
    checks ``viewStorage`` against the database, refuses when ``viewVersions``
    already lists a public version, POSTs ``/deposit/publish`` with the
    terms-dialog answers, and updates Storage with published_url and
    status="published" only after the public view URL responds.

    Prerequisites: status ``uploaded`` (plus sheet-only statuses) and no errors
    Success status: status="published"; status="updated_inventory" after Google Sheet update (if configured).
    """

    WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"

    def __init__(self) -> None:
        """Initialize the DataLumos publisher. Config from Args."""
        self._session = DataLumosBrowserSession()
        self._deposit_token = self._session.deposit_token

    def run(self, drpid: int) -> None:
        """
        Run the publish process for a single project.

        Implements ModuleProtocol. Gets project from Storage. For sheet-only
        statuses (not_found, no_links, skip presets, collector_hold - reason):
        updates Google Sheet only (no browser). For uploaded: validates
        datalumos_id, authenticates, runs publish
        flow, then updates sheet.

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
            gwda_error = self._nominate_gwda(page, get_field(project, "source_url"))
            if gwda_error:
                record_error(drpid, gwda_error)
                return
            self._session.ensure_authenticated()
            Logger.info(
                "Checking workspace Storage Status against database for DRPID=%s",
                drpid,
            )
            gate_error = self._pre_publish_gate(page, project, drpid)
            if gate_error:
                record_error(drpid, gate_error)
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
        except ProjectAbort:
            return
        except Exception as e:
            record_error(drpid, f"Publish failed: {e}")
            raise

        if not publish_ok:
            return

        # Sheet update is separate from browser publish. Failures stop this project.
        try:
            # Reload so sheet Dataset Size / fields reflect any post-collect updates.
            fresh = Storage.get(drpid) or project
            self._update_google_sheet_if_configured(drpid, fresh, workspace_id)
        except PipelineFatal:
            raise
        except Exception as e:
            record_error(
                drpid,
                f"Google Sheet update failed for DRPID={drpid} after successful publish: {e}",
            )

        self._finalize_after_publish(drpid)

    def close(self) -> None:
        """Close the browser kept open across the projects in this batch."""
        self._session.keep_deposit_token(self._deposit_token)
        self._session.close()

    def _nominate_gwda(self, page: Page, source_url: str) -> Optional[str]:
        """
        Nominate the project source URL to GWDA before publish.

        Args:
            page: Browser page for the nomination form.
            source_url: URL to nominate. Empty values are skipped.

        Returns:
            An error message when nomination fails, otherwise None.
        """
        if not source_url:
            return None
        nominator = GWDANominator(page, timeout=Args.upload_timeout)
        success, error = nominator.nominate(source_url)
        if success:
            return None
        return error or "GWDA nomination failed"

    def _open_project_workspace(self, page: Page, workspace_id: str) -> None:
        """
        Open the project workspace, signing in again if the profile lookup fails.

        Args:
            page: Playwright page for this publish.
            workspace_id: DataLumos project id.

        Raises:
            RuntimeError: When the workspace still lands on the login-error page.
        """
        if self._project_already_open(page, workspace_id):
            Logger.info(
                "DataLumos project %s is already open; not reloading the workspace",
                workspace_id,
            )
            return
        project_url = self._project_url(workspace_id)
        if not self._load_project_page(page, project_url):
            return
        Logger.warning(
            "DataLumos rejected the session after login; signing in again"
        )
        self._session.reauthenticate()
        if not self._load_project_page(page, project_url):
            return
        error = datalumos_session_error(page)
        if error:
            raise RuntimeError(error)

    def _load_project_page(self, page: Page, project_url: str) -> bool:
        """
        Navigate to a workspace URL and wait until its publish controls appear.

        A redirect to the login-error page can abort ``goto`` with
        ``net::ERR_ABORTED``. That abort is kept only when the resulting page
        is not the profile-retrieval error.

        Args:
            page: Playwright page.
            project_url: Workspace URL for one DataLumos project.

        Returns:
            True when the page is a login error and publish controls were not
            waited for.
        """
        aborted = self._goto_workspace(page, project_url)
        from upload.DataLumosAuthenticator import wait_for_human_verification

        wait_for_human_verification(page, timeout=60000)
        if datalumos_session_error(page) is not None:
            return True
        if aborted is not None:
            raise aborted
        self._wait_for_project_chrome(page, project_url)
        return False

    def _goto_workspace(self, page: Page, project_url: str) -> Optional[Exception]:
        """
        Start navigation to ``project_url``.

        Returns:
            The aborted-navigation exception when DataLumos cancelled the load,
            otherwise None.
        """
        try:
            page.goto(project_url, wait_until="domcontentloaded")
        except Exception as exc:
            if "ERR_ABORTED" not in str(exc):
                raise
            Logger.warning("Workspace navigation was aborted: %s", exc)
            return exc
        return None

    def _project_already_open(self, page: Page, workspace_id: str) -> bool:
        """Return True when this project page is already showing publish controls."""
        try:
            ready = page.evaluate(_PROJECT_READY_JS, workspace_id)
        except Exception:
            return False
        return ready is True

    def _wait_for_project_chrome(self, page: Page, project_url: str) -> None:
        """Wait until Storage Status and a publish button are on this project.

        The goToPath URL draws the workspace list first. This waits for that
        same page to show the project, and does not search the list.
        """
        workspace_id = _workspace_id_from_project_url(project_url)
        Logger.info(
            "Waiting for DataLumos project %s to show publish controls",
            workspace_id,
        )
        if self._publish_controls_ready(
            page, workspace_id, _PROJECT_CONTROLS_TIMEOUT_MS
        ):
            return
        raise RuntimeError(
            f"DataLumos project {workspace_id} did not show publish controls "
            f"within 5 minutes (url={page.url})"
        )

    def _publish_controls_ready(self, page: Page, workspace_id: str, timeout_ms: int) -> bool:
        """Return True when this project shows Storage Status and Publish Project."""
        try:
            page.wait_for_function(
                _PROJECT_READY_JS, arg=workspace_id, timeout=timeout_ms
            )
        except PlaywrightTimeoutError:
            return False
        return True

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

        Compares the Storage Status panel to ``num_files`` plus product folders
        and ``file_size`` before starting the publish click sequence.

        Args:
            page: Playwright page on the DataLumos project workspace.
            project: Storage project record.
            drpid: Project DRPID.

        Returns:
            Combined error message when mismatched; None when inventory matches.
        """
        try:
            errors = self._workspace_inventory_mismatches(page, project)
        except RuntimeError as exc:
            if not sign_in_required(exc):
                raise
            Logger.warning("DataLumos rejected the deposit token; signing in again")
            self._session.reauthenticate()
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
        Compare ``viewStorage`` to ``num_files`` plus product folders and ``file_size``.

        Args:
            page: Playwright page whose cookie jar is logged into DataLumos.
            project: Storage project record.

        Returns:
            Human-readable mismatch messages; empty when inventory matches.
        """
        from publisher.WorkspaceFileStats import mismatches_for_storage_status

        workspace_id = str(get_field(project, "datalumos_id") or "")
        if not workspace_id:
            return ["missing datalumos_id"]
        client = self._publish_client(page)
        try:
            status = client.storage_status(workspace_id)
            return mismatches_for_storage_status(status, project)
        finally:
            self._keep_deposit_token(client)

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

    def _version_title(self) -> str | None:
        """
        Optional version title sent with the publish POST.

        Returns:
            None for a first publish. Republish sets a title.
        """
        return None

    def _update_sheet_if_configured(
        self,
        drpid: int,
        project: Dict[str, Any],
        update_fn: "Callable[[], tuple[bool, Optional[str]]]",
        success_status: str,
    ) -> None:
        """
        If Google Sheet configured, run update_fn; on success set status to success_status.
        Missing credentials or libraries: record_crash. Other failures: record_error.
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
            record_error(drpid, "Google Sheet update skipped: no source_url")
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
            record_error(drpid, f"Google Sheet update failed: {error_message}")

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

        from publisher.inventory_sheet_updater import get_inventory_sheet_updater

        updater = get_inventory_sheet_updater()

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
        Other failures (e.g. API error): record an error and stop this project. If the source URL
        is not in the sheet, a new row is appended (see `GoogleSheetUpdater`).
        """
        from publisher.inventory_sheet_updater import get_inventory_sheet_updater

        updater = get_inventory_sheet_updater()

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
        Return a reason when DataLumos shows incomplete uploads.

        A file row with an empty size cell, or the text "File not available
        for download", means the upload did not finish. Folder rows are
        ignored: their type column is blank.
        """
        try:
            result = page.evaluate(_UPLOAD_READINESS_JS)
        except Exception as exc:
            Logger.warning(
                "Could not check upload readiness on project page: %s",
                exc,
            )
            return None
        return incomplete_upload_reason(result)

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

    def _publish_workspace(
        self,
        page: Page,
        drpid: int,
        *,
        retried: bool = False,
    ) -> tuple[bool, Optional[str]]:
        """
        Publish through the deposit API. A rejected token signs in once and retries.

        Returns:
            (True, None) on success, (False, error_message) on failure.
        """
        try:
            return self._publish_over_http(page, drpid)
        except RuntimeError as exc:
            if retried or not sign_in_required(exc):
                return False, str(exc)
            Logger.warning("DataLumos rejected the deposit token; signing in again")
            self._session.reauthenticate()
            return self._publish_workspace(page, drpid, retried=True)

    def _publish_over_http(self, page: Page, drpid: int) -> tuple[bool, Optional[str]]:
        """POST publish, then require the public view URL to respond."""
        project = Storage.get(drpid) or {}
        workspace_id = str(get_field(project, "datalumos_id") or "")
        client = self._publish_client(page)
        try:
            client.ensure_ready()
            blocked = self._block_if_already_published(client, workspace_id)
            if blocked:
                return False, blocked
            client.publish_project(workspace_id, self._version_title())
            view_url = self._published_view_url(workspace_id)
            if client.view_is_public(view_url):
                return True, None
            return False, f"Published view URL was not available: {view_url}"
        finally:
            self._keep_deposit_token(client)

    def _refuse_when_already_published(self) -> bool:
        """Return True when an existing public version must stop this publish."""
        return True

    def _block_if_already_published(self, client: Any, workspace_id: str) -> Optional[str]:
        """
        Return an error when posting publish would create another public version.

        Republish overrides ``_refuse_when_already_published`` and is allowed
        to post.

        Args:
            client: Deposit client for this batch.
            workspace_id: DataLumos project id.

        Returns:
            An error message when a public version already exists, else None.
        """
        if not self._refuse_when_already_published():
            return None
        labels = client.published_versions(workspace_id)
        if not labels:
            return None
        shown = ", ".join(labels)
        Logger.info(
            "DataLumos project %s is already published (%s); not posting /publish",
            workspace_id,
            shown,
        )
        return (
            f"DataLumos project {workspace_id} is already published ({shown}); "
            "refusing to publish again"
        )

    def _publish_client(self, page: Page) -> "DataLumosPublishClient":
        """Return a publish client that already has this batch's deposit token."""
        from publisher.DataLumosPublishClient import DataLumosPublishClient

        return DataLumosPublishClient(page, token=self._deposit_token)

    def _keep_deposit_token(self, client: "DataLumosPublishClient") -> None:
        """Remember the bearer token so the next project does not render the workspace."""
        self._deposit_token = client.token
        self._session.keep_deposit_token(client.token)

    def _reset_to_project_workspace(self, page: Page, workspace_id: str) -> None:
        """
        Navigate back to the project workspace before a publish retry.

        After a failed terms-dialog attempt the page is often still on
        ``reviewPublish`` (or inside the modal), where ``Publish Project``
        is not available.

        Args:
            page: Playwright page from the failed attempt.
            workspace_id: DataLumos project id.
        """
        if not workspace_id:
            page.wait_for_timeout(5000)
            return
        project_url = self._project_url(workspace_id)
        if self._project_already_open(page, workspace_id):
            Logger.info(
                "DataLumos project %s is already open; not reloading the workspace",
                workspace_id,
            )
            return
        self._load_project_page(page, project_url)

    def _click_publish_entry_button(self, page: Page) -> None:
        """
        Click the workspace button that starts the publish review flow.

        Args:
            page: Playwright page on the DataLumos project workspace.
        """
        Logger.info("Waiting for Publish Project button on workspace")
        publish_btn = page.locator("button.btn-primary:has-text('Publish Project')")
        publish_btn.wait_for(state="visible", timeout=int(Args.upload_timeout))
        publish_btn.scroll_into_view_if_needed()
        Logger.info("Clicking Publish Project")
        publish_btn.click()

    def _prepare_review_page(self, page: Page) -> None:
        """
        Optional review-page setup before Proceed to Publish.

        Default is a no-op; republish fills Version Title.

        Args:
            page: Playwright page on the review/publish URL.
        """
        return

    def _wait_for_review_page_ready(self, page: Page) -> None:
        """
        Wait until the review/publish page has loaded enough to Proceed safely.

        Clicking Proceed before metadata hydrates can open a Terms dialog where
        Publish Data stays disabled even though the fields look filled in the UI.

        Args:
            page: Playwright page on the reviewPublish URL.
        """
        self._wait_for_busy(page)
        proceed_btn = page.locator(
            "button.btn-primary:has-text('Proceed to Publish')"
        )
        proceed_btn.wait_for(state="visible", timeout=int(Args.upload_timeout))
        try:
            page.wait_for_load_state("networkidle", timeout=60000)
        except PlaywrightTimeoutError:
            Logger.warning(
                "networkidle timed out on review page; continuing after settle"
            )
        # Extra settle for React metadata panels (agency, summary, etc.).
        page.wait_for_timeout(2000)
        self._wait_for_busy(page)
        Logger.info("Review page ready for Proceed to Publish")

    def _run_publish_flow_once(self, page: Page, drpid: int) -> tuple[bool, Optional[str]]:
        """Run the publish flow once (no retry). Raises on failure."""
        timeout_ms = Args.upload_timeout

        # Step 1: Click publish / re-publish entry button
        self._wait_for_busy(page)
        self._click_publish_entry_button(page)

        # Step 2: Wait for review page (URL contains reviewPublish)
        try:
            page.wait_for_url(lambda url: "reviewPublish" in url, timeout=timeout_ms)
        except PlaywrightTimeoutError:
            err_text = self._check_errormsg(page)
            if err_text:
                raise RuntimeError(f"Error message on page: {err_text}")
            raise RuntimeError("Timeout waiting for review/publish page")

        # Let review metadata finish hydrating before Proceed — clicking too
        # early yields a Terms dialog with disabled Publish Data.
        self._wait_for_review_page_ready(page)

        # Step 2b: Optional review fields (e.g. version title on re-publish)
        self._prepare_review_page(page)

        # Step 3: Click "Proceed to Publish"
        self._wait_for_busy(page)
        Logger.info("Clicking Proceed to Publish")
        proceed_btn = page.locator("button.btn-primary:has-text('Proceed to Publish')")
        proceed_btn.wait_for(state="visible", timeout=timeout_ms)
        proceed_btn.click()
        page.wait_for_timeout(1000)

        # Step 4: Terms dialog (full disclosure form or short Publish Data only)
        self._wait_for_busy(page)
        terms = PublishTermsDialog()
        terms.complete(page)

        # Step 5: Click "Publish Data"
        self._wait_for_busy(page)
        terms.click_publish_data(page)

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
