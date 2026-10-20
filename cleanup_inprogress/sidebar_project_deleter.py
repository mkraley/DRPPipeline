"""Delete one DataLumos project from its direct workspace URL."""

import time
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from cleanup_inprogress.workspace_list import project_url

MORE_BUTTON = "button:has-text('more')"
DELETE_ITEM = (
    "div.btn-group:has(button:has-text('more')) "
    ">> ul.dropdown-menu.dropdown-sm >> li:has-text('Delete Project')"
)
CONFIRM_BUTTON = "#confirmationDialogYes"
_OPEN_TIMEOUT_MS = 45000
_MENU_TIMEOUT_MS = 15000
_READY_TIMEOUT_S = 20.0
_POLL_S = 0.5
_MORE_READY = """(() => {
  const more = [...document.querySelectorAll('button')]
    .some(button => (button.innerText || '').trim().toLowerCase() === 'more');
  return more ? 'ready' : '';
})()"""


class SidebarProjectDeleter:
    """Open a project by id and confirm Delete Project from the more menu."""

    def __init__(self, page: Page) -> None:
        """
        Args:
            page: Authenticated Playwright page.
        """
        self._page = page

    def delete_one(self, workspace_id: str) -> tuple[bool, str]:
        """
        Delete one project.

        Args:
            workspace_id: Numeric DataLumos project id.

        Returns:
            ``(True, detail)`` when the confirm button was clicked, otherwise
            ``(False, reason)``.
        """
        try:
            self._open_project(workspace_id)
        except PlaywrightTimeoutError:
            return False, "timeout opening project"
        if not self._open_more():
            return False, "more button not found"
        error = self._click_delete()
        if error:
            return False, error
        if not self._confirm():
            return False, "could not confirm delete"
        return True, "deleted"

    def _open_project(self, workspace_id: str) -> None:
        """Open the direct project URL and wait for the more button."""
        self._page.goto(
            project_url(workspace_id),
            wait_until="commit",
            timeout=_OPEN_TIMEOUT_MS,
        )
        if not self._project_menu_ready():
            raise PlaywrightTimeoutError("timeout opening project")
        self._release_hung_load()
        self._page.locator(MORE_BUTTON).first.wait_for(
            state="visible",
            timeout=_MENU_TIMEOUT_MS,
        )

    def _project_menu_ready(self) -> bool:
        """Return True once the project more button is in the DOM."""
        cdp = self._page.context.new_cdp_session(self._page)
        try:
            return self._poll_for_more(cdp)
        finally:
            cdp.detach()

    def _poll_for_more(self, cdp: Any) -> bool:
        """Poll the live document until the more button exists or time runs out."""
        deadline = time.monotonic() + _READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if self._more_button_present(cdp):
                return True
            self._page.wait_for_timeout(int(_POLL_S * 1000))
        return False

    def _more_button_present(self, cdp: Any) -> bool:
        """Return True when the document currently contains a more button."""
        result = cdp.send(
            "Runtime.evaluate",
            {"expression": _MORE_READY, "returnByValue": True},
        )
        value = (result.get("result") or {}).get("value")
        return value == "ready"

    def _release_hung_load(self) -> None:
        """Stop the workspace load event so later clicks are not blocked."""
        cdp = self._page.context.new_cdp_session(self._page)
        try:
            cdp.send("Runtime.evaluate", {"expression": "window.stop()"})
        finally:
            cdp.detach()

    def _open_more(self) -> bool:
        """Click the more button. Return False when it is missing."""
        more_button = self._page.locator(MORE_BUTTON)
        if more_button.count() == 0:
            return False
        try:
            more_button.first.click(timeout=_MENU_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return False
        return True

    def _click_delete(self) -> str:
        """
        Click Delete Project.

        Returns:
            Empty string on success, otherwise the failure reason.
        """
        delete_item = self._page.locator(DELETE_ITEM)
        if delete_item.count() == 0:
            return "Delete Project menu item not found"
        item = delete_item.first
        if "disabled" in (item.get_attribute("class") or ""):
            return "Delete Project is disabled"
        try:
            item.locator("a").first.click(timeout=_MENU_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return "could not click Delete Project"
        return ""

    def _confirm(self) -> bool:
        """Click the delete confirmation button."""
        confirm = self._page.locator(CONFIRM_BUTTON)
        try:
            confirm.first.wait_for(state="visible", timeout=_MENU_TIMEOUT_MS)
            confirm.first.click(timeout=_MENU_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            return False
        return True
