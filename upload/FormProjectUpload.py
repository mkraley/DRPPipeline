"""
Create a DataLumos project and fill metadata by clicking the workspace form.

``--ui-upload`` selects this path. The deposit API is the default.
"""

from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Page

from storage import Storage
from upload.DataLumosUploader import _agency_values_for_upload
from upload.UploadIssueReporter import UploadIssueReporter
from utils.Args import Args
from utils.Logger import Logger
from utils.PrincipalInvestigators import deserialize_investigators
from utils.project_utils import get_field


class FormProjectUpload:
    """Drive the New Project form for one authenticated page."""

    def __init__(self, page: Page, workspace_url: str) -> None:
        """
        Args:
            page: Authenticated Playwright page.
            workspace_url: DataLumos workspace URL.
        """
        self._page = page
        self._workspace_url = workspace_url

    def create_and_fill(
        self,
        project: dict[str, Any],
        drpid: int,
        reporter: UploadIssueReporter,
    ) -> str:
        """Create the project, store its id, fill metadata, and return the id."""
        form_filler = self._open_new_project(project, reporter)
        workspace_id = _workspace_id(self._page.url)
        Logger.info(f"Created project with workspace ID: {workspace_id}")
        Storage.update_record(drpid, {"datalumos_id": workspace_id})
        self._fill_fields(form_filler, project)
        return workspace_id

    def _open_new_project(self, project: dict[str, Any], reporter: UploadIssueReporter) -> Any:
        """Click New Project, save the title, and return the form filler."""
        from upload.DataLumosAuthenticator import wait_for_human_verification
        from upload.DataLumosFormFiller import DataLumosFormFiller
        from upload.UploadLargeFiles import WORKSPACE_LOAD_TIMEOUT_MS

        form_filler = DataLumosFormFiller(
            self._page, timeout=Args.upload_timeout, reporter=reporter
        )
        Logger.info("Navigating to DataLumos workspace")
        self._page.goto(self._workspace_url, wait_until="domcontentloaded")
        self._page.wait_for_load_state("networkidle", timeout=WORKSPACE_LOAD_TIMEOUT_MS)
        wait_for_human_verification(self._page, timeout=60000, reporter=reporter)
        new_project_btn = self._page.locator(".btn > span:nth-child(3)")
        form_filler.wait_for_obscuring_elements()
        new_project_btn.click()
        form_filler.fill_title(get_field(project, "title"))
        wait_for_human_verification(self._page, timeout=60000, reporter=reporter)
        return form_filler

    def _fill_fields(self, form_filler: Any, project: dict[str, Any]) -> None:
        """Fill the metadata sections on the project page just created."""
        form_filler.expand_all_sections()
        agencies = _agency_values_for_upload(
            get_field(project, "agency"),
            get_field(project, "office"),
        )
        if agencies:
            form_filler.fill_agency(agencies)
        investigators = deserialize_investigators(
            get_field(project, "principal_investigators")
        )
        if investigators:
            form_filler.fill_principal_investigators(investigators)
        form_filler.fill_summary(get_field(project, "summary"))
        form_filler.fill_original_url(get_field(project, "source_url"))
        keywords_raw = get_field(project, "keywords")
        if keywords_raw:
            form_filler.fill_keywords(_parse_keywords(keywords_raw))
        geographic = get_field(project, "geographic_coverage")
        if geographic:
            form_filler.fill_geographic_coverage(geographic)
        time_start = get_field(project, "time_start")
        time_end = get_field(project, "time_end")
        if time_start or time_end:
            form_filler.fill_time_period(time_start or None, time_end or None)
        data_types = get_field(project, "data_types")
        if data_types:
            form_filler.fill_data_types(data_types)
        notes = get_field(project, "collection_notes")
        download_date = get_field(project, "download_date")
        if notes or download_date:
            form_filler.fill_collection_notes(notes, download_date or None)


def _workspace_id(url: str) -> str:
    """Extract the workspace id from the project URL."""
    match = re.search(r"/datalumos/(\d+)", url)
    if not match:
        raise RuntimeError(f"Could not extract workspace ID from URL: {url}")
    return match.group(1)


def _parse_keywords(keywords_raw: str) -> list[str]:
    """Parse keywords split on commas or semicolons; strip ampersands from tokens."""
    cleaned = keywords_raw.replace("'", "").replace("[", "").replace("]", "").replace('"', "")
    parts = re.split(r"[,;]+", cleaned)
    return [token for part in parts if (token := part.strip().strip("&").strip())]
