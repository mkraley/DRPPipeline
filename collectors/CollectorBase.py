"""
Shared base class for DRP Pipeline data collectors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Any, FrozenSet

from storage import Storage
from utils.Args import Args
from utils.Errors import record_error
from utils.collector_status import merge_result_to_storage
from utils.file_utils import create_output_folder, folder_extensions_and_size, format_file_size
from utils.url_utils import access_url, is_valid_url


class CollectorBase(ABC):
    """
    Base orchestration for per-project collectors (ModuleProtocol ``run``).
    """

    _storage_skip_keys: FrozenSet[str] = frozenset()
    _storage_status_mode: str = "standard"

    def run(self, drpid: int) -> None:
        """
        Run collection for one project.

        Args:
            drpid: DRPID of the project to process.
        """
        record, source_url = self.load_project(drpid)
        if record is None or source_url is None:
            return
        try:
            result = self._collect(source_url, drpid, record)
            self.apply_result_to_storage(drpid, result)
        except Exception as exc:
            self.on_run_exception(drpid, exc)

    def load_project(self, drpid: int) -> tuple[dict[str, Any] | None, str | None]:
        """
        Load the project record and validate ``source_url``.

        Args:
            drpid: DRPID to load.

        Returns:
            Tuple of (record, source_url). Either element may be None on failure.
        """
        record = Storage.get(drpid)
        if record is None:
            record_error(
                drpid,
                f"Project record not found for DRPID: {drpid}",
                update_storage=False,
            )
            return None, None

        source_url = record.get("source_url")
        if not source_url:
            record_error(drpid, f"Missing source_url for DRPID: {drpid}")
            return record, None

        return record, str(source_url)

    def apply_result_to_storage(self, drpid: int, result: dict[str, Any]) -> None:
        """
        Merge a collection result into Storage using the subclass status mode.

        Args:
            drpid: Project DRPID.
            result: Collection fields keyed by Storage column names.
        """
        merge_result_to_storage(
            drpid,
            result,
            status_mode=self._storage_status_mode,
            skip_keys=self._storage_skip_keys,
        )

    def on_run_exception(self, drpid: int, exc: Exception) -> None:
        """
        Record an unexpected exception from ``run``.

        Args:
            drpid: Project DRPID.
            exc: Raised exception.
        """
        record_error(drpid, f"Exception during collection for DRPID {drpid}: {exc}")

    @abstractmethod
    def _collect(
        self,
        url: str,
        drpid: int,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Collect data for one project.

        Args:
            url: Source URL from Storage.
            drpid: Project DRPID.
            record: Full Storage record.

        Returns:
            Result dict keyed by Storage column names.
        """

    @staticmethod
    def validate_url(drpid: int, url: str) -> bool:
        """
        Return False and record an error when ``url`` is invalid.

        Args:
            drpid: Project DRPID for error logging.
            url: Candidate source URL.

        Returns:
            True when the URL passes ``is_valid_url``.
        """
        if is_valid_url(url):
            return True
        record_error(drpid, f"Invalid URL: {url}")
        return False

    @staticmethod
    def validate_url_accessible(drpid: int, url: str) -> bool:
        """
        Validate URL syntax and HTTP accessibility.

        Args:
            drpid: Project DRPID for error logging.
            url: Candidate source URL.

        Returns:
            True when the URL is valid and accessible.
        """
        if not CollectorBase.validate_url(drpid, url):
            return False
        access_success, status_msg = access_url(url)
        if access_success:
            return True
        record_error(drpid, f"URL access failed: {url} - {status_msg}")
        return False

    @staticmethod
    def create_project_folder(
        drpid: int,
        *,
        recreate: bool = True,
    ) -> Path | None:
        """
        Create the output folder for a project under ``Args.base_output_dir``.

        Args:
            drpid: Project DRPID used in the folder name.
            recreate: Passed to ``create_output_folder``.

        Returns:
            Folder path, or None when creation failed (error recorded).
        """
        folder_path = create_output_folder(Path(Args.base_output_dir), drpid, recreate=recreate)
        if folder_path:
            return folder_path
        record_error(drpid, "Failed to create output folder")
        return None

    @staticmethod
    def finalize_folder_stats(result: dict[str, Any], folder_path: Path) -> None:
        """
        Populate ``num_files``, ``file_size``, ``extensions``, and ``download_date``.

        Args:
            result: Mutable result dict.
            folder_path: Project output directory.
        """
        if not folder_path.is_dir():
            return
        extensions, total_bytes, num_files = folder_extensions_and_size(folder_path)
        result["num_files"] = num_files
        result["file_size"] = format_file_size(total_bytes)
        if extensions:
            result["extensions"] = extensions
        result["download_date"] = date.today().isoformat()
