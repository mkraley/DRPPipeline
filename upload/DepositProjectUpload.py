"""
Create a DataLumos project and post its metadata through the deposit API.

Production uploads use this path. It does not write a request log and does
not prefix the title. File bytes still go through the project page.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from playwright.sync_api import Page

from upload.DataLumosDepositClient import DataLumosDepositClient
from upload.DepositMetadata import metadata_from_project
from upload.DepositMetadataWriter import DepositMetadataWriter
from upload.UploadIssueReporter import UploadIssueReporter
from utils.project_utils import get_field
from utils.title_utils import normalize_inventory_title


class DepositProjectUpload:
    """Create one project and post its metadata without the workspace form."""

    def __init__(self, page: Page) -> None:
        """Args: page: Authenticated Playwright page."""
        self._page = page
        self._deposit: DataLumosDepositClient | None = None

    def create(
        self,
        project: dict[str, Any],
        reporter: Optional[UploadIssueReporter] = None,
    ) -> str:
        """
        Create the project and return its numeric workspace id.

        The id is available before metadata is posted, so the caller can store
        it if a later field fails.
        """
        metadata = metadata_from_project(project)
        _warn_if_title_truncated(project, metadata.title, reporter)
        path = self._client(reporter).create_project(metadata.title)
        return _workspace_id(path)

    def fill(self, workspace_id: str, project: dict[str, Any]) -> None:
        """Post metadata for a project created by :meth:`create`."""
        metadata = metadata_from_project(project)
        DepositMetadataWriter(self._client()).fill_metadata(
            f"/datalumos/{workspace_id}",
            metadata,
        )

    def _client(self, reporter: Optional[UploadIssueReporter] = None) -> DataLumosDepositClient:
        """Return the page client, opening the workspace on first use."""
        if self._deposit is None:
            self._deposit = DataLumosDepositClient(self._page, log_path=None)
            self._deposit.ensure_deposit_page(reporter)
        return self._deposit


def _workspace_id(path: str) -> str:
    """Read the numeric id from a ``/datalumos/{id}`` path."""
    match = re.search(r"/datalumos/(\d+)", path)
    if not match:
        raise RuntimeError(f"createProject did not return a workspace id: {path}")
    return match.group(1)


def _warn_if_title_truncated(
    project: dict[str, Any],
    written: str,
    reporter: Optional[UploadIssueReporter],
) -> None:
    """Record the same truncation warning the form filler records."""
    if reporter is None:
        return
    raw = get_field(project, "title")
    normalized = " ".join(normalize_inventory_title(raw).split())
    if len(written) < len(normalized):
        reporter.warn(
            f"Title truncated from {len(' '.join(raw.split()))} to "
            f"{len(written)} characters for DataLumos limit"
        )
