"""
National Park Service collector for DRP Pipeline.

Downloads public IRMA Digital Files for one sourced Project. Products become
subfolders; Data Table Info and landing-page JSON are written beside files.
Each Product is fetched and downloaded before the next one starts.
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
    fit_planned_files,
    planned_files_for_profile,
    unique_product_folder_name,
)
from collectors.NpsFileDownloader import NpsFileDownloader, count_files, folder_inventory
from collectors.NpsLandingMetadata import (
    PRODUCT_METADATA_NAME,
    PROJECT_METADATA_NAME,
    project_breadcrumb,
    write_landing_metadata,
)
from sourcing.NpsCatalogClient import NpsCatalogClient
from sourcing.NpsProjectMapper import product_breadcrumb_text, storage_updates_from_profile
from sourcing.NpsProfileMetadata import merge_doi_notes, profile_dois, profile_title
from sourcing.NpsReferenceRules import irma_project_id_from_source_url, reference_id_of
from storage.NpsHierarchyStore import NpsHierarchyStore
from utils.Args import Args
from utils.Errors import record_error, record_warning
from utils.Logger import Logger
from utils.file_utils import format_file_size


def _merge_collection_notes(
    existing: str,
    rename_notes: list[str],
    dois: list[str],
) -> str:
    """Combine sourcing notes, shortened-path originals, and DOI lines."""
    parts = [line for line in (existing or "").splitlines() if line.strip()]
    for note in rename_notes:
        cleaned = note.strip()
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    return merge_doi_notes("\n".join(parts), dois)


class NpsCollector(CollectorBase):
    """Collect public Digital Files for one IRMA Project, one Product at a time."""

    _storage_status_mode = "inventory"

    def __init__(
        self,
        *,
        client: NpsCatalogClient | None = None,
        hierarchy_store: NpsHierarchyStore | None = None,
        file_downloader: NpsFileDownloader | None = None,
        request_delay: float | None = None,
    ) -> None:
        """Initialize IRMA client, hierarchy store, and downloader."""
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
        products = store.list_products_for_drpid(drpid)
        Logger.info(
            "NPS DRPID %s: collecting IRMA Project %s (%s products)",
            drpid,
            project_id,
            len(products),
        )
        return self._collect_contents(
            drpid, project_id, products, folder_path, record, store
        )

    def _collect_contents(
        self,
        drpid: int,
        project_id: int,
        products: list[dict[str, Any]],
        folder_path: Path,
        record: dict[str, Any],
        store: NpsHierarchyStore,
    ) -> dict[str, Any]:
        """Fetch and download project files, then each Product in turn."""
        rename_notes: list[str] = []
        notes: list[str] = []
        all_files: list[NpsPlannedFile] = []
        product_profiles: list[tuple[str, dict[str, Any]]] = []
        crumb = project_breadcrumb(drpid, record, store)
        Logger.info("NPS DRPID %s: fetching project profile %s", drpid, project_id)
        project_profile = self._fetch_profile(drpid, project_id)
        files, batch_notes, skipped, _dir = self._ingest_profile(
            drpid, folder_path, project_profile, PROJECT_FILES_FOLDER, rename_notes
        )
        all_files.extend(files)
        notes.extend(batch_notes)
        if project_profile is not None:
            write_landing_metadata(
                folder_path / PROJECT_METADATA_NAME,
                project_profile,
                breadcrumb=crumb,
            )
        if not skipped:
            skipped = self._collect_products(
                drpid,
                products,
                folder_path,
                crumb,
                rename_notes,
                notes,
                all_files,
                product_profiles,
            )
        if not all_files:
            record_error(drpid, "No public Digital Files found for this IRMA Project")
            return {"folder_path": str(folder_path)}
        return self._finish_result(
            drpid,
            record,
            folder_path,
            store,
            project_profile,
            product_profiles,
            all_files,
            notes,
            skipped,
            rename_notes,
        )

    def _collect_products(
        self,
        drpid: int,
        products: list[dict[str, Any]],
        folder_path: Path,
        crumb: str,
        rename_notes: list[str],
        notes: list[str],
        all_files: list[NpsPlannedFile],
        product_profiles: list[tuple[str, dict[str, Any]]],
    ) -> bool:
        """Fetch, download, and write metadata for each Product sequentially."""
        used_folders: set[str] = set()
        total = len(products)
        for index, product in enumerate(products, 1):
            product_id = int(product["irma_product_id"])
            title = str(product.get("title") or "product")
            folder = unique_product_folder_name(title, used_folders, rename_notes)
            Logger.info(
                "NPS DRPID %s: product %s/%s %s (IRMA %s)",
                drpid,
                index,
                total,
                title,
                product_id,
            )
            profile = self._fetch_profile(drpid, product_id)
            if profile is None:
                continue
            files, batch_notes, skipped, folder = self._ingest_profile(
                drpid, folder_path, profile, folder, rename_notes
            )
            all_files.extend(files)
            notes.extend(batch_notes)
            product_profiles.append((folder, profile))
            write_landing_metadata(
                folder_path / folder / PRODUCT_METADATA_NAME,
                profile,
                breadcrumb=product_breadcrumb_text(
                    crumb,
                    product_id=reference_id_of(profile),
                    product_title=profile_title(profile),
                ),
            )
            if skipped:
                leftover = total - index
                if leftover:
                    Logger.info(
                        "NPS DRPID %s: stopping after product %s/%s (download budget)",
                        drpid,
                        index,
                        total,
                    )
                return True
        return False

    def _ingest_profile(
        self,
        drpid: int,
        folder_path: Path,
        profile: dict[str, Any] | None,
        relative_dir: str,
        rename_notes: list[str],
    ) -> tuple[list[NpsPlannedFile], list[str], bool, str]:
        """Plan, download, and write sidecars for one Project or Product profile."""
        if profile is None:
            return [], [], False, relative_dir
        planned = self._files_for_profile(drpid, profile, relative_dir)
        planned, path_notes, dir_renames = fit_planned_files(folder_path, planned)
        rename_notes.extend(path_notes)
        relative_dir = dir_renames.get(relative_dir, relative_dir)
        if not planned:
            return [], [], False, relative_dir
        notes, skipped, _bytes, _exts = self._file_downloader.download_files(
            drpid, folder_path, planned
        )
        notes.extend(write_sidecars_for_files(drpid, folder_path, planned, self._client))
        return planned, notes, skipped, relative_dir

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

    def _finish_result(
        self,
        drpid: int,
        record: dict[str, Any],
        folder_path: Path,
        store: NpsHierarchyStore,
        project_profile: dict[str, Any] | None,
        product_profiles: list[tuple[str, dict[str, Any]]],
        files: list[NpsPlannedFile],
        notes: list[str],
        skipped_large: bool,
        rename_notes: list[str],
    ) -> dict[str, Any]:
        """Write inventory fields after all Products have been processed."""
        result = self._inventory_result(record, folder_path, notes, skipped_large)
        store.update_public_file_count(drpid, int(result["num_files"]))
        if project_profile is not None:
            result.update(
                storage_updates_from_profile(
                    project_profile,
                    filenames=[entry.filename for entry in files],
                )
            )
        collection_notes = _merge_collection_notes(
            str(record.get("collection_notes") or ""),
            rename_notes,
            self._dois_from_profiles(project_profile, product_profiles),
        )
        if collection_notes:
            result["collection_notes"] = collection_notes
        Logger.info(
            "NPS collection complete for DRPID %s: %s files, %s",
            drpid,
            result.get("num_files"),
            result.get("file_size"),
        )
        return result

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
