"""
Cleanup In Progress: delete DataLumos projects in 'Deposit In Progress' state.

Implements ModuleProtocol.run(drpid) with drpid=-1 (single run, no Storage iteration).
Uses DataLumosBrowserSession: navigate to workspace, Hide inactive, list projects,
for each project verify status, open more dropdown, Delete Project, confirm.
"""

import re
from typing import List

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from upload.DataLumosBrowserSession import DataLumosBrowserSession
from utils.Args import Args
from utils.Logger import Logger


WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"
PROJECT_URL_TEMPLATE = "https://www.datalumos.org/datalumos/workspace?goToLevel=project&goToPath=/datalumos/{workspace_id}"
DEPOSIT_IN_PROGRESS_TEXT = "[Deposit In Progress]"


class CleanupInProgress:
    """
    Deletes DataLumos workspace projects in 'Deposit In Progress' state.

    Implements ModuleProtocol. run(-1) is called once: authenticates, goes to
    workspace, clicks Hide inactive, iterates ul.list-group items, and for each
    project in Deposit In Progress deletes it via the more dropdown and confirmation.
    """

    def __init__(self) -> None:
        """Initialize. Config from Args (upload credentials, timeout)."""
        self._session = DataLumosBrowserSession()

    def run(self, drpid: int) -> None:
        """
        Run cleanup: find and delete all projects in Deposit In Progress.

        Implements ModuleProtocol. drpid is ignored (use -1). Does not read/write Storage.

        Args:
            drpid: Ignored; module runs once over the DataLumos UI.
        """
        Logger.info("Cleanup In Progress: starting")
        page = self._session.ensure_browser()
        self._session.ensure_authenticated()

        try:
            page.goto(WORKSPACE_URL, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=120000)

            from upload.DataLumosAuthenticator import wait_for_human_verification
            wait_for_human_verification(page, timeout=60000)

            self._click_hide_inactive(page)
            project_ids = self._get_project_ids_from_list(page)
            Logger.info(f"Cleanup In Progress: found {len(project_ids)} project(s) in list")

            for workspace_id in project_ids:
                self._process_one_project(page, workspace_id)

        finally:
            self._session.close()
        Logger.info("Cleanup In Progress: finished")

    def _click_hide_inactive(self, page: Page) -> None:
        """Click the 'Hide inactive' radio so only active (e.g. In Progress) projects show."""
        hide_label = page.locator('label:has-text("Hide inactive")')
        try:
            hide_label.first.click(timeout=Args.upload_timeout)
            page.wait_for_timeout(1000)
        except PlaywrightTimeoutError:
            Logger.warning("Hide inactive control not found or not clickable")

    def _get_project_ids_from_list(self, page: Page) -> List[str]:
        """Return workspace IDs from ul.list-group > li links (href like .../datalumos/123)."""
        ids: List[str] = []
        list_group = page.locator("ul.list-group")
        if list_group.count() == 0:
            return ids
        items = list_group.locator("li")
        count = items.count()
        for idx in range(count):
            li = items.nth(idx)
            link = li.locator("a[href*='/datalumos/']").first
            if link.count() == 0:
                continue
            href = link.get_attribute("href") or ""
            match = re.search(r"/datalumos/(\d+)", href)
            if match:
                ids.append(match.group(1))
        return ids

    def _process_one_project(self, page: Page, workspace_id: str) -> None:
        """
        Open project, verify Deposit In Progress, delete via dropdown and confirm.

        On mismatch or disabled Delete: log error and return. Otherwise delete and re-apply Hide inactive.
        """
        project_url = PROJECT_URL_TEMPLATE.format(workspace_id=workspace_id)
        try:
            page.goto(project_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=Args.upload_timeout)
            page.wait_for_timeout(1500)
        except PlaywrightTimeoutError:
            Logger.error(f"Cleanup In Progress: timeout loading project {workspace_id}")
            return

        if not self._confirm_deposit_in_progress(page, workspace_id):
            return

        if not self._open_more_dropdown(page, workspace_id):
            return

        delete_btn = page.locator(
            "ul.dropdown-menu.dropdown-sm >> li >> a:has-text('Delete Project')"
        ).first
        if delete_btn.count() == 0:
            Logger.error(f"Cleanup In Progress: Delete Project menu item not found for {workspace_id}")
            return
        parent_li = delete_btn.locator("xpath=..")
        if parent_li.get_attribute("class") and "disabled" in (parent_li.get_attribute("class") or ""):
            Logger.error(f"Cleanup In Progress: Delete Project is disabled for {workspace_id}")
            return

        try:
            delete_btn.click()
            page.wait_for_timeout(500)
        except PlaywrightTimeoutError:
            Logger.error(f"Cleanup In Progress: could not click Delete Project for {workspace_id}")
            return

        confirm_btn = page.locator("#confirmationDialogYes")
        try:
            if confirm_btn.count() > 0:
                confirm_btn.first.click()
                page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            Logger.error(f"Cleanup In Progress: could not confirm delete for {workspace_id}")
            return

        self._click_hide_inactive(page)
        Logger.info(f"Cleanup In Progress: deleted project {workspace_id}")

    def _open_more_dropdown(self, page: Page, workspace_id: str) -> bool:
        """Open the 'more' dropdown that contains Delete Project. Return False if not found."""
        dropdown = page.locator(".dropdown:has(ul.dropdown-menu.dropdown-sm)")
        if dropdown.count() == 0:
            Logger.error(f"Cleanup In Progress: more dropdown not found for {workspace_id}")
            return False
        toggle = dropdown.locator("button, a[href]").first
        if toggle.count() == 0:
            Logger.error(f"Cleanup In Progress: more dropdown toggle not found for {workspace_id}")
            return False
        try:
            toggle.click()
            page.wait_for_timeout(400)
        except PlaywrightTimeoutError:
            Logger.error(f"Cleanup In Progress: could not open more dropdown for {workspace_id}")
            return False
        return True

    def _confirm_deposit_in_progress(self, page: Page, workspace_id: str) -> bool:
        """
        Return True if the third sibling span of h1 has text [Deposit In Progress]; else log error and return False.
        """
        third_span = page.locator("xpath=//h1/following-sibling::span[3]")
        if third_span.count() == 0:
            Logger.error(
                f"Cleanup In Progress: project {workspace_id} has no third sibling span of h1 (wrong page?)"
            )
            return False
        text = third_span.first.inner_text()
        if DEPOSIT_IN_PROGRESS_TEXT not in (text or ""):
            Logger.error(
                f"Cleanup In Progress: project {workspace_id} status is not [Deposit In Progress]: {text!r}"
            )
            return False
        return True
