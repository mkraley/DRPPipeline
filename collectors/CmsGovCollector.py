"""
CMS.gov Collector for DRP Pipeline.

Collects data from data.cms.gov dataset pages, e.g.:
  https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals/hospital-service-area

Flow:
  1. /data-api/v1/slug?path=<url_path>
       → dataset name, taxonomy UUID, current-version UUID, nav topic
  2. /data-api/v1/dataset/<current_uuid>/resources
       → most-recent Primary file + ancillary files (Data Dictionary, Methodology)
  3. /data-api/v1/dataset-type/<taxonomy_uuid>/resources
       → all historical Primary files across every release year
  4. Playwright browser render of source_url
       → description text (in div.DatasetPage__summary-field-summary-container,
         not exposed by any API endpoint)
"""

from collectors.CollectorBase import CollectorBase
from collectors.PlaywrightSession import PlaywrightSession
from utils.Errors import record_error, record_warning
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import requests

from utils.Logger import Logger
from utils.download_with_progress import download_via_url
from utils.file_utils import (
    folder_extensions_and_size,
    format_file_size,
    sanitize_filename,
)
from utils.url_utils import BROWSER_HEADERS

_API_BASE = "https://data.cms.gov/data-api/v1"


_DESCRIPTION_SELECTOR = "[class*='DatasetPage__summary-field-summary-container']"


class CmsGovCollector(CollectorBase):
    """
    Collector for data.cms.gov dataset pages.

    Uses the data-api/v1 REST endpoints to extract metadata and download
    all historical Primary files plus ancillary files. Uses Playwright to
    scrape the description, which is only available in the rendered page.
    """

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._session = PlaywrightSession(headless=headless)
        self._last_resources_error: str = ""

    def run(self, drpid: int) -> None:
        """Run collection and always release the browser session."""
        try:
            super().run(drpid)
        finally:
            self._cleanup_browser()

    def _collect(
        self,
        url: str,
        drpid: int,
        record: dict[str, Any],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        if not self.validate_url(drpid, url):
            return result

        url_path = self._extract_path(url)
        if not url_path:
            record_error(drpid, f"Cannot extract path from URL: {url}")
            return result

        slug_data = self._fetch_slug(url_path)
        if not slug_data:
            record_error(drpid, f"Slug API returned nothing for path: {url_path}")
            return result

        result.update(self._parse_slug_metadata(slug_data))

        description = self._scrape_description(url, drpid)
        if description:
            result["summary"] = description

        current_uuid = (slug_data.get("current_dataset") or {}).get("uuid")
        taxonomy_uuid = slug_data.get("uuid")

        if not current_uuid:
            record_error(drpid, "Slug API response missing current_dataset.uuid")
            return result

        folder_path = self.create_project_folder(drpid)
        if folder_path is None:
            return result
        # Normalize to POSIX-style paths so tests and downstream consumers are
        # consistent across platforms.
        result["folder_path"] = folder_path.as_posix()

        # Collect files: all historical Primary files + ancillaries (once each)
        all_files = self._gather_files(drpid, current_uuid, taxonomy_uuid)
        if all_files is None:
            # Resources API failure already recorded via record_error.
            return result
        if not all_files:
            record_warning(drpid, "No files found to download")
        else:
            self._download_files(drpid, all_files, folder_path)

        # Infer time_start / time_end from dataset_version_date on Primary resources.
        # This is more accurate than current_dataset.version (which only reflects the
        # latest release) and avoids using last_modified_date (website update date).
        date_range = self._extract_date_range(all_files)
        if date_range.get("time_start"):
            result["time_start"] = date_range["time_start"]
        if date_range.get("time_end"):
            result["time_end"] = date_range["time_end"]

        exts, total_bytes, num_files = folder_extensions_and_size(folder_path)
        result["num_files"] = num_files
        if exts:
            result["extensions"] = ",".join(exts)
            tabular = {".csv", ".tsv", ".xlsx", ".xls"}
            result["data_types"] = "tabular" if any(e in tabular for e in exts) else "other"
        if total_bytes:
            result["file_size"] = format_file_size(total_bytes)

        result["download_date"] = date.today().isoformat()
        return result

    def _extract_path(self, url: str) -> Optional[str]:
        """Return the path component of url (e.g. '/provider-summary-by.../hospital-service-area')."""
        parsed = urlparse(url)
        return parsed.path if parsed.path and parsed.path != "/" else None

    def _fetch_slug(self, url_path: str) -> Optional[Dict[str, Any]]:
        api_url = f"{_API_BASE}/slug?path={quote(url_path)}"
        Logger.info("Fetching CMS slug: %s", api_url)
        try:
            resp = requests.get(api_url, headers=BROWSER_HEADERS, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            return body.get("data")
        except Exception as exc:
            Logger.error("CMS slug API error: %s", exc)
            return None

    def _fetch_resources(self, endpoint: str) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch a CMS resources API endpoint.

        Args:
            endpoint: Full resources API URL.

        Returns:
            Resource dicts on success (possibly empty), or None when the request fails.
            On failure, ``_last_resources_error`` holds the message for ``record_error``.
        """
        Logger.info("Fetching CMS resources: %s", endpoint)
        try:
            resp = requests.get(endpoint, headers=BROWSER_HEADERS, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            return body.get("data") or []
        except Exception as exc:
            self._last_resources_error = (
                f"CMS resources API error ({endpoint}): {exc}"
            )
            return None

    def _require_resources(
        self, drpid: int, endpoint: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch resources and record an error when the API request fails.

        Args:
            drpid: Project DRPID.
            endpoint: Full resources API URL.

        Returns:
            Resource list on success, or None after recording an error.
        """
        resources = self._fetch_resources(endpoint)
        if resources is None:
            record_error(
                drpid,
                self._last_resources_error
                or f"CMS resources API error ({endpoint})",
            )
        return resources

    def _parse_slug_metadata(self, slug_data: Dict[str, Any]) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}

        name = slug_data.get("name")
        if name:
            fields["title"] = name

        fields["agency"] = "Centers for Medicare & Medicaid Services"

        nav_topic = slug_data.get("nav_topic") or {}
        kws = []
        topic_name = nav_topic.get("name")
        if topic_name:
            kws.append(topic_name)
        if name and name not in kws:
            kws.append(name)
        if kws:
            fields["keywords"] = ", ".join(kws)

        current = slug_data.get("current_dataset") or {}
        version = current.get("version")
        if version:
            fields["time_end"] = version
        last_modified = current.get("last_modified_date")
        if last_modified:
            fields["time_end"] = last_modified

        return fields

    def _gather_files(
        self,
        drpid: int,
        current_uuid: str,
        taxonomy_uuid: Optional[str],
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Return a deduplicated list of file dicts to download.

        Uses /dataset/{current_uuid}/resources for the current Primary file
        and ancillaries (Data Dictionary, Methodology, etc.).

        If taxonomy_uuid is available, also fetches /dataset-type/{taxonomy_uuid}/resources
        for all historical Primary files.

        Args:
            drpid: Project DRPID (for error recording).
            current_uuid: Current dataset UUID.
            taxonomy_uuid: Optional dataset-type UUID for historical Primaries.

        Returns:
            File resource dicts, an empty list when the API succeeds with no files,
            or None when a resources API request fails (error already recorded).
        """
        current_endpoint = f"{_API_BASE}/dataset/{current_uuid}/resources"
        current_resources = self._require_resources(drpid, current_endpoint)
        if current_resources is None:
            return None

        # Collect ancillary files from current resources (deduplicated by file_uuid)
        seen_uuids: set = set()
        files: List[Dict[str, Any]] = []

        # Historical Primary files via dataset-type (all years)
        if taxonomy_uuid:
            taxonomy_endpoint = (
                f"{_API_BASE}/dataset-type/{taxonomy_uuid}/resources"
            )
            all_resources = self._require_resources(drpid, taxonomy_endpoint)
            if all_resources is None:
                return None
            for r in all_resources:
                if r.get("type") == "Primary" and r.get("file_url"):
                    fid = r.get("file_uuid") or r.get("file_url")
                    if fid not in seen_uuids:
                        seen_uuids.add(fid)
                        files.append(r)
        else:
            # Fall back to current resources Primary only
            for r in current_resources:
                if r.get("type") == "Primary" and r.get("file_url"):
                    fid = r.get("file_uuid") or r.get("file_url")
                    if fid not in seen_uuids:
                        seen_uuids.add(fid)
                        files.append(r)

        # Ancillary files from current resources (Data Dictionary, Methodology, etc.)
        for r in current_resources:
            if r.get("type") != "Primary" and r.get("file_url"):
                fid = r.get("file_uuid") or r.get("file_url")
                if fid not in seen_uuids:
                    seen_uuids.add(fid)
                    files.append(r)

        if not files:
            record_warning(drpid, "No downloadable files found in API response")

        return files

    def _download_files(
        self,
        drpid: int,
        files: List[Dict[str, Any]],
        folder_path: Path,
    ) -> None:
        for resource in files:
            file_url = resource.get("file_url", "")
            raw_name = resource.get("file_name") or file_url.split("/")[-1].split("?")[0]
            filename = sanitize_filename(raw_name) if raw_name else "dataset"
            dest = folder_path / filename

            if dest.exists():
                Logger.info("Skipping already-downloaded: %s", filename)
                continue

            Logger.info(
                "Downloading [%s] %s → %s",
                resource.get("type", "?"),
                file_url,
                filename,
            )
            try:
                _bytes, success = download_via_url(file_url, dest)
                if not success:
                    record_warning(drpid, f"Download failed: {file_url}")
            except Exception as exc:
                record_warning(drpid, f"Download error for {file_url}: {exc}")

    def _extract_date_range(self, files: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Extract time_start and time_end from Primary resource version dates.

        Uses dataset_version_date on Primary resources (e.g. "2013-12-31", "2016-12-01").
        Returns the earliest as time_start and latest as time_end.
        Returns an empty dict if no Primary resources have a dataset_version_date.
        """
        dates = sorted(
            f["dataset_version_date"]
            for f in files
            if f.get("type") == "Primary" and f.get("dataset_version_date")
        )
        if not dates:
            return {}
        return {"time_start": dates[0], "time_end": dates[-1]}

    def _scrape_description(self, url: str, drpid: int) -> Optional[str]:
        """Render source_url with Playwright and extract the dataset description."""
        if not self._init_browser():
            record_warning(drpid, "Browser unavailable; description not collected")
            return None
        page = self._session.page
        assert page is not None
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            el = page.query_selector(_DESCRIPTION_SELECTOR)
            if el:
                text = el.inner_text().strip()
                return text if text else None
            record_warning(drpid, "Description element not found on page")
            return None
        except Exception as exc:
            record_warning(drpid, f"Failed to scrape description: {exc}")
            return None

    def _init_browser(self) -> bool:
        return self._session.start()

    def _cleanup_browser(self) -> None:
        self._session.close()
