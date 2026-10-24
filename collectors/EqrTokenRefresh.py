"""Replace stale EQR zip URLs before a resumed download."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from collectors.EqrZipCatalog import EqrZipCatalog
from collectors.EqrZipLink import EqrZipLink
from storage.ProjectFileStore import ProjectFileRow, ProjectFileStore
from utils.Errors import abort_project
from utils.Logger import Logger

_EQR_HOST = "eqrreportviewer.ferc.gov"
LinkSource = Callable[[], list[EqrZipLink]]


def pending_after_eqr_refresh(drpid: int, store: ProjectFileStore) -> list[ProjectFileRow]:
    """
    Refresh EQR zip URLs, then return the rows that still need downloading.

    Other hosts are left unchanged. The viewer puts a path token in each zip
    URL, and that token is read again because a later resume can outlast it.

    Args:
        drpid: Project DRPID.
        store: File-row store for the open database.

    Returns:
        Pending download rows, with EQR URLs rewritten when the viewer has them.
    """
    pending = store.list_pending_downloads(drpid)
    if not any(is_eqr_zip_url(row.source_url) for row in pending):
        return pending
    refresh_eqr_download_urls(drpid, store, EqrZipCatalog().list_links)
    return store.list_pending_downloads(drpid)


def refresh_eqr_download_urls(drpid: int, store: ProjectFileStore, list_links: LinkSource) -> None:
    """
    Rewrite pending EQR ``source_url`` values from a fresh viewer link list.

    Args:
        drpid: Project DRPID.
        store: File-row store for the open database.
        list_links: Callable that returns the current CSV zip links.
    """
    current = {link.name.upper(): link for link in list_links()}
    if not current:
        abort_project(drpid, "EQR viewer returned no CSV quarterly zip links")
    pending = [row for row in store.list_pending_downloads(drpid) if is_eqr_zip_url(row.source_url)]
    if _rewrite_rows(drpid, store, pending, current) == 0:
        abort_project(drpid, "EQR viewer links did not match any pending CSV zip")


def is_eqr_zip_url(url: str) -> bool:
    """Return True for a quarterly CSV zip on the EQR viewer."""
    lowered = url.lower()
    return _EQR_HOST in lowered and "/csv/" in lowered


def _rewrite_rows(
    drpid: int,
    store: ProjectFileStore,
    pending: list[ProjectFileRow],
    current: dict[str, EqrZipLink],
) -> int:
    """Replace stored URLs that differ from the fresh viewer links."""
    matched = 0
    for row in pending:
        link = current.get(Path(row.relative_path).name.upper())
        if link is None:
            Logger.warning("DRPID %s: no fresh EQR link for %s", drpid, row.relative_path)
            continue
        matched += 1
        if link.url != row.source_url:
            store.update_source_url(drpid, row.relative_path, link.url)
            Logger.info("Refreshed EQR URL for %s", row.relative_path)
    return matched
