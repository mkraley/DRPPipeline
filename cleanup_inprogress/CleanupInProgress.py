"""
Cleanup In Progress: delete DataLumos projects in 'Deposit In Progress' state.

Implements ModuleProtocol.run(drpid) with drpid=-1 (single run, no Storage iteration).
Opens the workspace once, snapshots the Hide-inactive sidebar, then deletes each
candidate via the deposit ``DELETE /deletePath`` API (no per-project page opens).
"""

from typing import List, Set

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from cleanup_inprogress.workspace_list import (
    published_sidebar_labels,
    workspace_ids_from_sidebar,
)
from storage import Storage
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from upload.DataLumosDepositClient import DataLumosDepositClient
from utils.Args import Args
from utils.Logger import Logger


WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"
_PROJECT_LIST = "ul.list-group"
_PROJECT_LIST_TIMEOUT_MS = 300000


class CleanupInProgress:
    """
    Deletes DataLumos workspace projects in 'Deposit In Progress' state.

    Implements ModuleProtocol. run(-1) authenticates once, clicks Hide inactive,
    snapshots the sidebar, and deletes each unprotected id via the deposit API.
    """

    def __init__(self) -> None:
        """Initialize. Config from Args (upload credentials, timeout)."""
        self._session = DataLumosBrowserSession()

    def run(self, drpid: int) -> None:
        """
        Run cleanup: snapshot in-progress projects and delete them via API.

        Implements ModuleProtocol. drpid is ignored (use -1). Does not write Storage.
        Reads Storage only to resolve ``--keep-ids`` DRPIDs to DataLumos workspace IDs.

        Args:
            drpid: Ignored; module runs once over the DataLumos workspace list.
        """
        Logger.info("Cleanup In Progress: starting")
        keep_workspace_ids = resolve_keep_workspace_ids(Args.keep_ids or [])
        if keep_workspace_ids:
            Logger.info(
                "Cleanup In Progress: protecting %s DataLumos deposit(s) via --keep-ids",
                len(keep_workspace_ids),
            )
        page = self._session.ensure_browser()
        self._session.ensure_authenticated()

        try:
            self._run_cleanup(page, keep_workspace_ids)
        finally:
            self._session.close()
        Logger.info("Cleanup In Progress: finished")

    def _run_cleanup(self, page: Page, keep_workspace_ids: Set[str]) -> None:
        """Hide inactive, snapshot ids, then API-delete unprotected projects."""
        page.goto(WORKSPACE_URL, wait_until="domcontentloaded")
        from upload.DataLumosAuthenticator import wait_for_human_verification

        wait_for_human_verification(page, timeout=60000)
        # Hide inactive first: the first ul.list-group is often a hidden empty
        # placeholder until the filter shows active deposits.
        self._click_hide_inactive(page)
        if not self._wait_for_list_or_log(page):
            return
        project_ids = self._snapshot_project_ids(page)
        if project_ids is None:
            return
        targets = [wid for wid in project_ids if wid not in keep_workspace_ids]
        skipped = len(project_ids) - len(targets)
        if skipped:
            Logger.info(
                "Cleanup In Progress: skipping %s protected deposit(s) (--keep-ids)",
                skipped,
            )
        Logger.info(
            "Cleanup In Progress: deleting %s project(s) via deposit API",
            len(targets),
        )
        self._delete_via_api(page, targets)

    def _wait_for_list_or_log(self, page: Page) -> bool:
        """Wait for the visible list; log and return False on timeout."""
        try:
            self._wait_for_project_list(page)
        except PlaywrightTimeoutError:
            Logger.error(
                "Cleanup In Progress: workspace project list did not become "
                "visible within %sms (ul.list-group stayed hidden or empty)",
                _PROJECT_LIST_TIMEOUT_MS,
            )
            return False
        return True

    def _snapshot_project_ids(self, page: Page) -> List[str] | None:
        """
        Read sidebar HTML once and return project ids.

        Returns None when (Published) appears after Hide inactive — that is a
        hard error and cleanup must not continue.
        """
        html = self._snapshot_list_html(page)
        published = published_sidebar_labels(html)
        if published:
            Logger.error(
                "Cleanup In Progress: (Published) still visible after Hide "
                "inactive (%s label(s)); aborting without deletes. First: %s",
                len(published),
                published[0][:120],
            )
            return None
        project_ids = workspace_ids_from_sidebar(html)
        Logger.info(
            "Cleanup In Progress: found %s project(s) in Hide-inactive list",
            len(project_ids),
        )
        return project_ids

    def _delete_via_api(self, page: Page, workspace_ids: List[str]) -> None:
        """Delete each workspace id with DELETE /deletePath; continue on failure."""
        client = DataLumosDepositClient(page, token=self._session.deposit_token)
        client.ensure_deposit_page()
        if client.token:
            self._session.keep_deposit_token(client.token)
        for workspace_id in workspace_ids:
            self._delete_one(client, workspace_id)

    def _delete_one(self, client: DataLumosDepositClient, workspace_id: str) -> None:
        """Delete one project path; log success or failure without aborting."""
        path = f"/datalumos/{workspace_id}"
        try:
            client.delete_path(path)
        except Exception as exc:
            Logger.error(
                "Cleanup In Progress: failed to delete %s: %s",
                workspace_id,
                exc,
            )
            return
        Logger.info("Cleanup In Progress: deleted project %s", workspace_id)

    def _snapshot_list_html(self, page: Page) -> str:
        """Return inner HTML of the visible project list, or empty string."""
        list_group = self._project_list_locator(page)
        if list_group.count() == 0:
            list_group = page.locator(_PROJECT_LIST).filter(has=page.locator("li a"))
        if list_group.count() == 0:
            return ""
        return list_group.first.inner_html() or ""

    def _project_list_locator(self, page: Page) -> Locator:
        """
        Locator for the visible sidebar list that contains project links.

        The workspace DOM can include a hidden empty ``ul.list-group`` before the
        real list; prefer a visible list that already has ``li a`` children.
        """
        return page.locator(_PROJECT_LIST).filter(has=page.locator("li a")).locator(
            "visible=true"
        )

    def _wait_for_project_list(self, page: Page) -> None:
        """Wait until a visible workspace project list with links is present."""
        self._project_list_locator(page).first.wait_for(
            state="visible",
            timeout=_PROJECT_LIST_TIMEOUT_MS,
        )

    def _click_hide_inactive(self, page: Page) -> None:
        """Click the 'Hide inactive' radio so only active projects show."""
        hide_label = page.locator('label:has-text("Hide inactive")')
        try:
            hide_label.first.click(timeout=Args.upload_timeout)
            page.wait_for_timeout(1000)
        except PlaywrightTimeoutError:
            Logger.warning("Hide inactive control not found or not clickable")


def resolve_keep_workspace_ids(keep_drpids: List[int]) -> Set[str]:
    """
    Map ``--keep-ids`` DRPIDs to DataLumos workspace ID strings via Storage.

    Logs a warning for each DRPID that is missing or has no ``datalumos_id``.
    """
    workspace_ids: Set[str] = set()
    for drpid in keep_drpids:
        record = Storage.get(drpid)
        if not record:
            Logger.warning(
                "Cleanup In Progress: --keep-ids DRPID=%s not found in database",
                drpid,
            )
            continue
        raw = record.get("datalumos_id")
        workspace_id = str(raw).strip() if raw is not None else ""
        if not workspace_id:
            Logger.warning(
                "Cleanup In Progress: --keep-ids DRPID=%s has no datalumos_id; cannot protect",
                drpid,
            )
            continue
        workspace_ids.add(workspace_id)
        Logger.info(
            "Cleanup In Progress: will keep DRPID=%s (datalumos_id=%s)",
            drpid,
            workspace_id,
        )
    return workspace_ids
