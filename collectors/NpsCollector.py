"""
National Park Service collector for DRP Pipeline.

Downloads public IRMA Digital Files for one sourced Project. Products become
subfolders; Data Table Info and landing-page JSON are written beside files.
Run via orchestrator when ``Args.source`` is ``nps``::

    python main.py collector --source nps
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any

from collectors.BtsMetadataExtractor import infer_data_types
from collectors.CollectorBase import CollectorBase
from collectors.NpsDataTableSidecar import write_sidecars_for_files
from collectors.NpsDownloadPlan import (
    PROJECT_FILES_FOLDER,
    NpsPlannedFile,
    planned_files_for_profile,
    unique_product_folder_name,
)
from collectors.NpsFileDownloader import NpsFileDownloader, count_files, folder_inventory
from collectors.NpsLandingMetadata import (
    project_breadcrumb,
    write_project_and_product_landing_files,
)
from sourcing.NpsCatalogClient import NpsCatalogClient
from sourcing.NpsProjectMapper import storage_updates_from_profile
from sourcing.NpsProfileMetadata import merge_doi_notes, profile_dois
from sourcing.NpsReferenceRules import irma_project_id_from_source_url
from storage.NpsHierarchyStore import NpsHierarchyStore
from utils.Args import Args
from utils.Errors import record_error, record_warning
from utils.Logger import Logger
from utils.file_utils import format_file_size


class NpsCollector(CollectorBase):
    """Collect public Digital Files for one IRMA Project."""

    _storage_status_mode = "inventory"

    def __init__(
        self,
        *,
        client: NpsCatalogClient | None = None,
        hierarchy_store: NpsHierarchyStore | None = None,
        file_downloader: NpsFileDownloader | None = None,
        request_delay: float | None = None,
    ) -> None:
        """
        Initialize the collector.

        Args:
            client: IRMA client (created when omitted).
            hierarchy_store: Program/Product tables (created when omitted).
            file_downloader: Digital File downloader (created when omitted).
            request_delay: Seconds between IRMA calls.
        """
        self._client = client or NpsCatalogClient()
        self._hierarchy_store = hierarchy_store
        self._file_downloader = file_downloader or NpsFileDownloader()
        default_delay = float(getattr(Args, "nps_request_delay", 0.1) or 0.1)
        self._request_delay = request_delay if request_delay is not None else default_delay

    def _collect(
        self,
        url: str,
        drpid: int,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """Collect public files for one sourced IRMA Project."""
        project_id = irma_project_id_from_source_url(url)
        if project_id is None:
            record_error(drpid, f"Not an IRMA Profile URL: {url}")
            return {}
        folder_path = self.create_project_folder(drpid)
        if folder_path is None:
            return {}
        store = self._hierarchy_store or NpsHierarchyStore.from_storage()
        project_profile, product_profiles, files = self._gather(drpid, project_id, store)
        if not files:
            record_error(drpid, "No public Digital Files found for this IRMA Project")
            return {"folder_path": str(folder_path)}
        notes, skipped_large, _bytes, _exts = self._file_downloader.download_files(
            drpid, folder_path, files
        )
        notes.extend(write_sidecars_for_files(drpid, folder_path, files, self._client))
        write_project_and_product_landing_files(
            folder_path,
            project_profile,
            product_profiles,
            project_breadcrumb(drpid, record, store),
        )
        result = self._inventory_result(record, folder_path, notes, skipped_large)
        store.update_public_file_count(drpid, int(result["num_files"]))
        if project_profile is not None:
            result.update(
                storage_updates_from_profile(
                    project_profile,
                    filenames=[entry.filename for entry in files],
                )
            )
        doi_notes = merge_doi_notes(
            str(record.get("collection_notes") or ""),
            self._dois_from_profiles(project_profile, product_profiles),
        )
        if doi_notes:
            result["collection_notes"] = doi_notes
        Logger.info(
            "NPS collection complete for DRPID %s: %s files, %s",
            drpid,
            result.get("num_files"),
            result.get("file_size"),
        )
        return result

    def _gather(
        self,
        drpid: int,
        project_id: int,
        store: NpsHierarchyStore,
    ) -> tuple[dict[str, Any] | None, list[tuple[str, dict[str, Any]]], list[NpsPlannedFile]]:
        """Fetch profiles and build the download list for one Project."""
        planned: list[NpsPlannedFile] = []
        product_profiles: list[tuple[str, dict[str, Any]]] = []
        used_folders: set[str] = set()
        project_profile = self._fetch_profile(drpid, project_id)
        if project_profile is not None:
            planned.extend(self._files_for_profile(drpid, project_profile, PROJECT_FILES_FOLDER))
        for product in store.list_products_for_drpid(drpid):
            product_id = int(product["irma_product_id"])
            folder = unique_product_folder_name(str(product.get("title") or "product"), used_folders)
            profile = self._fetch_profile(drpid, product_id)
            if profile is None:
                continue
            product_profiles.append((folder, profile))
            planned.extend(self._files_for_profile(drpid, profile, folder))
        return project_profile, product_profiles, planned

    def _dois_from_profiles(
        self,
        project_profile: dict[str, Any] | None,
        product_profiles: list[tuple[str, dict[str, Any]]],
    ) -> list[str]:
        """Collect unique DOIs from the Project and Product landing pages."""
        dois: list[str] = []
        profiles = [project_profile] if project_profile is not None else []
        profiles.extend(profile for _folder, profile in product_profiles)
        for profile in profiles:
            for doi in profile_dois(profile):
                if doi not in dois:
                    dois.append(doi)
        return dois

    def _files_for_profile(
        self,
        drpid: int,
        profile: dict[str, Any],
        relative_dir: str,
    ) -> list[NpsPlannedFile]:
        """Attach holdings metadata and return planned files for one profile."""
        reference_id = profile.get("referenceId")
        holdings: list[dict[str, Any]] = []
        if reference_id is not None:
            self._pause()
            try:
                holdings = self._client.fetch_holdings(int(reference_id))
            except RuntimeError as exc:
                record_warning(drpid, f"GetHoldings failed for {reference_id}: {exc}")
        return planned_files_for_profile(profile, relative_dir, holdings)

    def _fetch_profile(self, drpid: int, reference_id: int) -> dict[str, Any] | None:
        """Fetch one IRMA Profile, recording a warning on failure."""
        self._pause()
        try:
            return self._client.fetch_profile(reference_id)
        except RuntimeError as exc:
            record_warning(drpid, f"IRMA Profile {reference_id} failed: {exc}")
            return None

    def _inventory_result(
        self,
        record: dict[str, Any],
        folder_path: Path,
        notes: list[str],
        skipped_large: bool,
    ) -> dict[str, Any]:
        """Fill inventory fields from on-disk files and sourced metadata."""
        total_bytes, extensions = folder_inventory(folder_path)
        result: dict[str, Any] = {
            "folder_path": str(folder_path),
            "download_date": date.today().isoformat(),
            "num_files": count_files(folder_path),
            "file_size": format_file_size(total_bytes),
            "_skipped_large_file": skipped_large,
        }
        if extensions:
            result["extensions"] = ", ".join(sorted(extensions))
        data_types = infer_data_types(
            str(record.get("title") or ""),
            str(record.get("summary") or ""),
            str(record.get("keywords") or ""),
            "",
            file_extensions=extensions,
        )
        if data_types:
            result["data_types"] = data_types
        if notes:
            result["status_notes"] = "\n".join(notes)
        return result

    def _pause(self) -> None:
        """Sleep between IRMA requests when a delay is configured."""
        if self._request_delay > 0:
            time.sleep(self._request_delay)
