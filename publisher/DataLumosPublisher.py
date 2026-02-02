"""
DataLumos publisher module.

Implements ModuleProtocol to publish uploaded projects in DataLumos.
Coordinates browser lifecycle, authentication, and the publish workflow.
Publish flow derived from chiara_upload.py (Selenium) → Playwright.
"""

from typing import Any, Dict, Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright, TimeoutError as PlaywrightTimeoutError

from storage import Storage
from utils.Args import Args
from utils.Errors import record_error
from utils.Logger import Logger


# Published project URL template (same as Download Location in chiara_upload update_google_sheet)
PUBLISHED_URL_TEMPLATE = "https://www.datalumos.org/datalumos/project/{workspace_id}/version/V1/view"


class DataLumosPublisher:
    """
    Publisher module that publishes uploaded projects in DataLumos.

    Implements ModuleProtocol. For each eligible project (status="upload"),
    this module: authenticates, navigates to the project, runs the publish
    workflow (Publish Project → review → Proceed to Publish → dialog →
    Publish Data → Back to Project), and updates Storage with published_url
    and status="publisher".

    Prerequisites: status="upload" and no errors
    Success status: status="publisher"
    """

    WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"

    def __init__(self) -> None:
        """Initialize the DataLumos publisher. Config from Args."""
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._authenticated = False

    def run(self, drpid: int) -> None:
        """
        Run the publish process for a single project.

        Implements ModuleProtocol. Gets project from Storage, validates
        datalumos_id, authenticates, navigates to project, runs publish flow,
        and updates Storage on success.

        Args:
            drpid: The DRPID of the project to publish.
        """
        Logger.info(f"Starting publish for DRPID={drpid}")

        project = Storage.get(drpid)
        if project is None:
            record_error(drpid, f"Project with DRPID={drpid} not found in Storage")
            return

        workspace_id = self._get_field(project, "datalumos_id")
        if not workspace_id:
            record_error(drpid, "Missing datalumos_id; project must be uploaded before publish")
            return

        try:
            page = self._ensure_browser()
            self._ensure_authenticated()

            project_url = self._project_url(workspace_id)
            page.goto(project_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=120000)

            from upload.DataLumosAuthenticator import wait_for_human_verification
            wait_for_human_verification(page, timeout=60000)

            success, error_message = self._publish_workspace(page, drpid)
            if not success:
                record_error(drpid, error_message or "Publish workflow failed")
                return

            published_url = PUBLISHED_URL_TEMPLATE.format(workspace_id=workspace_id)
            Storage.update_record(drpid, {
                "published_url": published_url,
                "status": "publisher",
            })
            Logger.info(f"Publish completed for DRPID={drpid}, published_url={published_url}")
        except Exception as e:
            record_error(drpid, f"Publish failed: {e}")
            raise
        finally:
            self.close()

    def _get_field(self, project: Dict[str, Any], key: str) -> str:
        """Get and trim a project field. Returns empty string if missing."""
        return (project.get(key) or "").strip()

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

    def _ensure_browser(self) -> Page:
        """Ensure browser is initialized and return the page."""
        if self._page is not None:
            return self._page

        Logger.debug("Initializing Playwright browser")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=Args.upload_headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        self._context = self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        self._context.set_default_timeout(Args.upload_timeout)
        self._page = self._context.new_page()
        return self._page

    def _ensure_authenticated(self) -> None:
        """Ensure user is authenticated to DataLumos."""
        if self._authenticated:
            return

        from upload.DataLumosAuthenticator import DataLumosAuthenticator

        page = self._ensure_browser()
        authenticator = DataLumosAuthenticator(page, timeout=Args.upload_timeout)

        if not Args.datalumos_username or not Args.datalumos_password:
            raise RuntimeError(
                "DataLumos credentials not configured. "
                "Set datalumos_username and datalumos_password in config."
            )

        authenticator.authenticate(Args.datalumos_username, Args.datalumos_password)
        self._authenticated = True

    def close(self) -> None:
        """Close the browser and clean up resources."""
        if self._page is not None:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None

        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        self._authenticated = False
        Logger.debug("Browser resources cleaned up")
