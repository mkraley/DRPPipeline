"""
Shared Google Sheets inventory update logic for publisher modules.

Subclasses implement format-specific column names and cell values (data inventories
vs Baserow batch import). Row matching is always by exact source URL.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.Args import Args
from utils.google_sheets_service import build_sheets_v4_service
from utils.Logger import Logger

try:
    from google.oauth2 import service_account
    from googleapiclient.errors import HttpError

    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False
    HttpError = Exception  # type: ignore[misc, assignment]

DOWNLOAD_LOCATION_TEMPLATE = (
    "https://www.datalumos.org/datalumos/project/{workspace_id}/version/{version}/view"
)


class InventorySheetUpdaterBase(ABC):
    """
    Base class for inventory sheet updaters.

    Finds rows by exact URL match and appends when no row exists. Subclasses supply
    required column lists and request builders for their spreadsheet format.
    """

    def update(
        self,
        source_url: str,
        workspace_id: str,
        project: Dict[str, Any],
        version: str = "V1",
    ) -> tuple[bool, Optional[str]]:
        """
        Update the sheet row matching ``source_url`` with publishing results.

        Args:
            source_url: Source URL to match in the URL column.
            workspace_id: DataLumos workspace ID for Download Location.
            project: Project dict from storage.
            version: DataLumos version segment (``V1`` or ``V2``).

        Returns:
            ``(True, None)`` on success, ``(False, error_message)`` on failure.
        """

        def _build(
            sheet_name: str,
            row_number: int,
            column_map: Dict[str, str],
            append_new_row: bool,
            source_url: str,
            title_to_write: Optional[str],
            agency_to_write: Optional[str],
            office_to_write: Optional[str],
            workspace_id: str,
            project: Dict[str, Any],
            username: str,
            version: str = "V1",
            **kwargs: Any,
        ) -> List[Dict[str, Any]]:
            return self._build_update_requests(
                sheet_name,
                row_number,
                column_map,
                workspace_id,
                project,
                username,
                source_url_for_new_row=source_url if append_new_row else "",
                title_to_write=title_to_write or "",
                agency_to_write=agency_to_write or "",
                office_to_write=office_to_write or "",
                version=version,
            )

        return self._update_row(
            source_url=source_url,
            required_columns=self._required_columns_publish(),
            optional_columns=self._optional_columns_publish(),
            build_requests=_build,
            workspace_id=workspace_id,
            project=project,
            username=Args.google_username or "",
            version=version,
        )

    def update_for_not_found_or_no_links(
        self,
        source_url: str,
        notes_value: str,
    ) -> tuple[bool, Optional[str]]:
        """Update the sheet for ``not_found`` / ``no_links`` sheet-only paths."""
        return self.update_for_sheet_only(
            source_url=source_url,
            notes_value=notes_value,
            dataset_download_possible="N",
            log_suffix=" (not_found/no_links)",
        )

    def update_for_sheet_only(
        self,
        source_url: str,
        notes_value: str,
        dataset_download_possible: str = "N",
        project: Optional[Dict[str, Any]] = None,
        log_suffix: str = "",
        write_claimed: bool = True,
    ) -> tuple[bool, Optional[str]]:
        """
        Update the sheet for sheet-only publisher paths.

        Args:
            source_url: Source URL row key.
            notes_value: Notes column text.
            dataset_download_possible: Used by data-inventories format only.
            project: Optional project metadata for title/agency/office columns.
            log_suffix: Log message suffix.
            write_claimed: When True, write the claim/contact column.

        Returns:
            ``(True, None)`` on success, ``(False, error_message)`` on failure.
        """
        required = self._required_columns_sheet_only(write_claimed=write_claimed)
        return self._update_row(
            source_url=source_url,
            required_columns=required,
            optional_columns=self._optional_columns_sheet_only(),
            build_requests=self._build_sheet_only_requests,
            log_suffix=log_suffix,
            notes_value=notes_value,
            dataset_download_possible=dataset_download_possible,
            project=project,
            write_claimed=write_claimed,
        )

    def update_claimed(
        self,
        source_url: str,
        project: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, Optional[str]]:
        """Set the claim/contact column for ``source_url``."""
        return self._update_row(
            source_url=source_url,
            required_columns=self._required_columns_claimed(),
            optional_columns=self._optional_columns_claimed(),
            build_requests=self._build_claimed_only_requests,
            log_suffix=" (claimed)",
            project=project,
        )

    @abstractmethod
    def _required_columns_publish(self) -> List[str]:
        """Required header names for a successful publish update."""

    @abstractmethod
    def _optional_columns_publish(self) -> List[str]:
        """Optional header names for a successful publish update."""

    @abstractmethod
    def _required_columns_sheet_only(self, *, write_claimed: bool) -> List[str]:
        """Required header names for sheet-only updates."""

    @abstractmethod
    def _optional_columns_sheet_only(self) -> List[str]:
        """Optional header names for sheet-only updates."""

    @abstractmethod
    def _required_columns_claimed(self) -> List[str]:
        """Required header names for claim-only updates."""

    @abstractmethod
    def _optional_columns_claimed(self) -> List[str]:
        """Optional header names for claim-only updates."""

    @abstractmethod
    def _resolve_metadata_for_row(
        self,
        service: Any,
        sheet_id: str,
        sheet_name: str,
        row_number: int,
        append_new: bool,
        column_map: Dict[str, str],
        project: Optional[Dict[str, Any]],
    ) -> tuple[str, str, str]:
        """
        Return ``(title, agency, office)`` metadata to pass to request builders.

        Subclasses map project fields to their format's title and org columns.
        """

    @abstractmethod
    def _build_update_requests(
        self,
        sheet_name: str,
        row_number: int,
        column_map: Dict[str, str],
        workspace_id: str,
        project: Dict[str, Any],
        username: str,
        source_url_for_new_row: str = "",
        title_to_write: str = "",
        agency_to_write: str = "",
        office_to_write: str = "",
        version: str = "V1",
    ) -> List[Dict[str, Any]]:
        """Build batchUpdate cells for a publish update."""

    @abstractmethod
    def _build_sheet_only_requests(
        self,
        sheet_name: str,
        row_number: int,
        column_map: Dict[str, str],
        append_new_row: bool,
        source_url: str,
        notes_value: str,
        dataset_download_possible: str = "N",
        title_to_write: str = "",
        agency_to_write: str = "",
        office_to_write: str = "",
        service: Any = None,
        sheet_id: str = "",
        write_claimed: bool = True,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Build batchUpdate cells for sheet-only updates."""

    @abstractmethod
    def _build_claimed_only_requests(
        self,
        sheet_name: str,
        row_number: int,
        column_map: Dict[str, str],
        append_new_row: bool,
        source_url: str,
        title_to_write: str = "",
        agency_to_write: str = "",
        office_to_write: str = "",
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Build batchUpdate cells for claim-only updates."""

    def _update_row(
        self,
        source_url: str,
        required_columns: List[str],
        optional_columns: Optional[List[str]],
        build_requests: Callable[..., List[Dict[str, Any]]],
        log_suffix: str = "",
        **build_kwargs: Any,
    ) -> Tuple[bool, Optional[str]]:
        """Validate config, locate row by URL, build requests, and batchUpdate."""
        if not GOOGLE_SHEETS_AVAILABLE:
            return False, (
                "Google Sheets API not installed. "
                "Install with: pip install google-api-python-client google-auth google-auth-httplib2"
            )

        sheet_id = Args.google_sheet_id
        credentials_path = Path(Args.google_credentials) if Args.google_credentials else None
        sheet_name = Args.google_sheet_name

        if not sheet_id or not credentials_path:
            return False, "Google Sheet ID and credentials path are required"

        if not source_url or not source_url.strip():
            return False, "Source URL is required to find matching row"

        try:
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path),
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            service = build_sheets_v4_service(credentials, cache_discovery=False)

            column_map = self._get_column_mapping(
                service, sheet_id, sheet_name, required_columns, optional_columns
            )
            if not column_map:
                raise ValueError("Failed to get column mapping from Google Sheet")
            url_col_letter = column_map.get("URL")
            if not url_col_letter:
                raise ValueError("Could not find URL column in sheet")

            row_number = self._find_row_by_url(
                service, sheet_id, sheet_name, url_col_letter, source_url.strip()
            )
            append_new = False
            if not row_number:
                row_number = self._get_next_append_row(
                    service, sheet_id, sheet_name, url_col_letter
                )
                append_new = True
                Logger.info(
                    f"No sheet row matches source URL; appending at row {row_number}{log_suffix}"
                )

            Logger.debug(
                f"{'Appending' if append_new else 'Updating'} Google Sheet row {row_number}{log_suffix}"
            )

            project = build_kwargs.get("project")
            project_dict = project if isinstance(project, dict) else None
            title_to_write, agency_to_write, office_to_write = self._resolve_metadata_for_row(
                service,
                sheet_id,
                sheet_name,
                row_number,
                append_new,
                column_map,
                project_dict,
            )

            update_requests = build_requests(
                sheet_name=sheet_name,
                row_number=row_number,
                column_map=column_map,
                append_new_row=append_new,
                source_url=source_url.strip(),
                title_to_write=title_to_write,
                agency_to_write=agency_to_write,
                office_to_write=office_to_write,
                service=service,
                sheet_id=sheet_id,
                **build_kwargs,
            )
            if not update_requests:
                return False, "No data to update"

            body = {"valueInputOption": "USER_ENTERED", "data": update_requests}
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet_id,
                body=body,
            ).execute()

            action = "Appended" if append_new else "Updated"
            Logger.info(
                f"{action} Google Sheet row {row_number}{log_suffix} with {len(update_requests)} columns"
            )
            return True, None

        except ValueError as exc:
            return False, str(exc)
        except FileNotFoundError:
            return False, f"Credentials file not found: {credentials_path}"
        except HttpError as exc:
            return False, f"Google Sheets API error: {exc}"
        except Exception as exc:
            Logger.warning(f"Error updating Google Sheet{log_suffix}: {exc}")
            return False, str(exc)

    def _column_index_to_letter(self, col_index: int) -> str:
        """Convert 1-based column index to letter (e.g. 1 -> A, 27 -> AA)."""
        result = ""
        while col_index > 0:
            col_index -= 1
            result = chr(65 + (col_index % 26)) + result
            col_index //= 26
        return result

    def _get_next_column_letter(
        self, service: Any, sheet_id: str, sheet_name: str
    ) -> str:
        """Return the letter for the column after the last existing header column."""
        range_name = f"{sheet_name}!1:1"
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        num_cols = len(values[0]) if values and values[0] else 0
        return self._column_index_to_letter(num_cols + 1)

    def _get_column_mapping(
        self,
        service: Any,
        sheet_id: str,
        sheet_name: str,
        required_columns: List[str],
        optional_columns: Optional[List[str]] = None,
    ) -> Optional[Dict[str, str]]:
        """Read header row and map logical column names to letters."""
        range_name = f"{sheet_name}!1:1"
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        if not values:
            raise ValueError(
                f"Sheet '{sheet_name}' has no header row (row 1 is empty). "
                "Ensure the sheet has column headers in the first row."
            )

        column_map: Dict[str, str] = {}
        for idx, col_name in enumerate(values[0]):
            if col_name and str(col_name).strip():
                column_map[str(col_name).strip()] = self._column_index_to_letter(idx + 1)

        found_columns: Dict[str, str] = {}
        missing: List[str] = []

        for required in required_columns:
            found = False
            for col_name, col_letter in column_map.items():
                if col_name.lower() == required.lower():
                    found_columns[required] = col_letter
                    found = True
                    break
            if not found:
                for col_name, col_letter in column_map.items():
                    if (
                        required.lower() in col_name.lower()
                        or col_name.lower() in required.lower()
                    ):
                        found_columns[required] = col_letter
                        found = True
                        break
            if not found:
                missing.append(required)

        if missing:
            raise ValueError(
                f"Required columns not found in sheet '{sheet_name}': {missing}. "
                f"Available: {list(column_map.keys())}"
            )

        for opt in optional_columns or []:
            if opt in found_columns:
                continue
            for col_name, col_letter in column_map.items():
                if col_name.lower() == opt.lower():
                    found_columns[opt] = col_letter
                    break
            else:
                for col_name, col_letter in column_map.items():
                    if (
                        opt.lower() in col_name.lower()
                        or col_name.lower() in opt.lower()
                    ):
                        found_columns[opt] = col_letter
                        break

        return found_columns

    def _find_row_by_url(
        self,
        service: Any,
        sheet_id: str,
        sheet_name: str,
        url_column_letter: str,
        source_url: str,
    ) -> Optional[int]:
        """Return 1-based row number with an exact URL match, or None."""
        range_name = f"{sheet_name}!{url_column_letter}2:{url_column_letter}"
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        source_clean = source_url.strip().lower()
        if not source_clean:
            return None

        for idx, row in enumerate(values):
            if row and len(row) > 0:
                cell_url = str(row[0]).strip().lower()
                if cell_url and cell_url == source_clean:
                    return idx + 2

        return None

    def _get_next_append_row(
        self,
        service: Any,
        sheet_id: str,
        sheet_name: str,
        url_column_letter: str,
    ) -> int:
        """Return the 1-based row number for a new URL row append."""
        range_name = f"{sheet_name}!{url_column_letter}2:{url_column_letter}"
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        return 2 + len(values)

    def _read_cell_text(
        self,
        service: Any,
        sheet_id: str,
        sheet_name: str,
        col_letter: str,
        row_number: int,
    ) -> str:
        """Return trimmed string for a single cell, or empty if blank."""
        rng = f"{sheet_name}!{col_letter}{row_number}"
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=rng)
            .execute()
        )
        values = result.get("values", [])
        if not values or not values[0]:
            return ""
        return str(values[0][0]).strip()

    def _metadata_value_if_cell_empty(
        self,
        service: Any,
        sheet_id: str,
        sheet_name: str,
        row_number: int,
        append_new: bool,
        column_map: Dict[str, str],
        project: Optional[Dict[str, Any]],
        column_key: str,
        project_field: str,
        *,
        transform: Callable[[str], str] | None = None,
    ) -> Optional[str]:
        """
        Return project metadata when the target cell is empty or on a new row.

        Args:
            service: Google Sheets API service.
            sheet_id: Spreadsheet ID.
            sheet_name: Worksheet tab name.
            row_number: 1-based row to inspect/write.
            append_new: True when appending a new row.
            column_map: Logical column to letter mapping.
            project: Project dict from storage.
            column_key: Logical column name in ``column_map``.
            project_field: Key on ``project`` to read.
            transform: Optional post-process for the project value.

        Returns:
            Value to write, or None when nothing should be written.
        """
        if not project:
            return None
        col_letter = column_map.get(column_key)
        if not col_letter:
            return None
        val = (project.get(project_field) or "").strip()
        if not val:
            return None
        if transform is not None:
            val = transform(val)
            if not val:
                return None
        if append_new:
            return val
        if not self._read_cell_text(service, sheet_id, sheet_name, col_letter, row_number):
            return val
        return None
