"""Open a DataLumos project from the workspace list.

A project URL sometimes leaves the deposit app on My Projects. The list
search box can open the project that URL did not.
"""

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.Logger import Logger


_SEARCH = "input[placeholder*='Search within workspace']"
_LIST_PROBE_MS = 2000
_LINK_TIMEOUT_MS = 15000


class WorkspaceListOpener:
    """Click a project in the DataLumos workspace list."""

    def open_if_list_showing(self, page: Page, workspace_id: str) -> bool:
        """
        Open ``workspace_id`` when the workspace project list is on screen.

        Args:
            page: Playwright page, possibly showing My Projects.
            workspace_id: Numeric DataLumos project id.

        Returns:
            True when a matching project link was clicked.
        """
        if not self._list_is_showing(page):
            return False
        Logger.warning(
            "DataLumos project %s is still the workspace list (url=%s); "
            "opening it from the list",
            workspace_id,
            page.url,
        )
        self._search_for_project(page, workspace_id)
        return self._click_project(page, workspace_id)

    def _list_is_showing(self, page: Page) -> bool:
        """Return True when the workspace search box is visible."""
        search = page.locator(_SEARCH)
        try:
            if search.count() == 0:
                return False
            return bool(search.first.is_visible(timeout=_LIST_PROBE_MS))
        except PlaywrightTimeoutError:
            return False

    def _search_for_project(self, page: Page, workspace_id: str) -> None:
        """Type the project id into the workspace search box."""
        page.locator(_SEARCH).first.fill(workspace_id)
        Logger.info(
            "Searched the workspace list for DataLumos project %s",
            workspace_id,
        )

    def _click_project(self, page: Page, workspace_id: str) -> bool:
        """Click the list link for this project. Return False when it is absent."""
        label = f"datalumos-{workspace_id}"
        link = page.locator(f"a:has-text('{label}')")
        try:
            link.first.wait_for(state="visible", timeout=_LINK_TIMEOUT_MS)
        except PlaywrightTimeoutError:
            Logger.error(
                "Workspace list has no link for %s (url=%s)",
                label,
                page.url,
            )
            return False
        Logger.info("Clicking workspace list entry %s", label)
        link.first.click()
        return True
