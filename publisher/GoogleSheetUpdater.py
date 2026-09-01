"""
Google Sheet updater for the data inventories spreadsheet format.

Updates a shared inventory tab by matching source URL and writing Claimed, Data Added,
Download Location, and related columns. Logic derived from chiara_upload.update_google_sheet().
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.Args import Args
from utils.file_utils import format_file_size
from utils.title_utils import normalize_inventory_title

from publisher.inventory_sheet_updater_base import (
    DOWNLOAD_LOCATION_TEMPLATE,
    GOOGLE_SHEETS_AVAILABLE,
    InventorySheetUpdaterBase,
)

# Re-export for existing tests and imports.
_GOOGLE_SHEETS_AVAILABLE = GOOGLE_SHEETS_AVAILABLE

_REQUIRED_COLUMNS = [
    "URL",
    "Claimed",
    "Data Added",
    "Dataset Download Possible?",
    "Nominated to EOT / USGWDA",
    "Date Downloaded",
    "Download Location",
    "Dataset Size",
    "File extensions of data uploads",
    "Metadata availability info",
]

_REQUIRED_COLUMNS_NOT_FOUND = [
    "URL",
    "Claimed",
    "Data Added",
    "Dataset Download Possible?",
    "Nominated to EOT / USGWDA",
]

_OPTIONAL_METADATA_COLUMNS = ["Title of Site", "Title", "Agency", "Office"]


class GoogleSheetUpdater(InventorySheetUpdaterBase):
    """
    Updates the data inventories Google Sheet with publishing results.

    Finds the row by matching ``source_url`` in the URL column, then writes Claimed,
    Data Added, Download Location, Date Downloaded, and related fields. Appends a
    new row when no exact URL match exists.
    """

    def _required_columns_publish(self) -> List[str]:
        return list(_REQUIRED_COLUMNS)

    def _optional_columns_publish(self) -> List[str]:
        return list(_OPTIONAL_METADATA_COLUMNS)

    def _required_columns_sheet_only(self, *, write_claimed: bool) -> List[str]:
        required = list(_REQUIRED_COLUMNS_NOT_FOUND)
        if not write_claimed:
            required = [column for column in required if column != "Claimed"]
        return required

    def _optional_columns_sheet_only(self) -> List[str]:
        return ["Notes", *_OPTIONAL_METADATA_COLUMNS]

    def _required_columns_claimed(self) -> List[str]:
        return ["URL", "Claimed"]

    def _optional_columns_claimed(self) -> List[str]:
        return list(_OPTIONAL_METADATA_COLUMNS)

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
        title = self._metadata_value_if_cell_empty(
            service,
            sheet_id,
            sheet_name,
            row_number,
            append_new,
            column_map,
            project,
            "Title of Site",
            "title",
            transform=normalize_inventory_title,
        )
        if not title:
            title = self._metadata_value_if_cell_empty(
                service,
                sheet_id,
                sheet_name,
                row_number,
                append_new,
                column_map,
                project,
                "Title",
                "title",
                transform=normalize_inventory_title,
            )
        agency = self._metadata_value_if_cell_empty(
            service,
            sheet_id,
            sheet_name,
            row_number,
            append_new,
            column_map,
            project,
            "Agency",
            "agency",
        )
        office = self._metadata_value_if_cell_empty(
            service,
            sheet_id,
            sheet_name,
            row_number,
            append_new,
            column_map,
            project,
            "Office",
            "office",
        )
        return title or "", agency or "", office or ""

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
        """Build update requests that set only Claimed (plus URL on append)."""
        username = Args.google_username or ""
        requests: List[Dict[str, Any]] = []

        url = (source_url or "").strip()
        if append_new_row and url and column_map.get("URL"):
            requests.append({
                "range": f"{sheet_name}!{column_map['URL']}{row_number}",
                "values": [[url]],
            })

        self._append_metadata_requests(
            requests,
            sheet_name,
            row_number,
            column_map,
            title_to_write,
            agency_to_write,
            office_to_write,
        )

        if column_map.get("Claimed"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Claimed']}{row_number}",
                "values": [[username]],
            })
        return requests

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
        """Build update requests for sheet-only inventory updates."""
        username = Args.google_username or ""
        requests: List[Dict[str, Any]] = []

        url = (source_url or "").strip()
        if append_new_row and url and column_map.get("URL"):
            requests.append({
                "range": f"{sheet_name}!{column_map['URL']}{row_number}",
                "values": [[url]],
            })

        self._append_metadata_requests(
            requests,
            sheet_name,
            row_number,
            column_map,
            title_to_write,
            agency_to_write,
            office_to_write,
        )

        download_possible = (dataset_download_possible or "N").strip() or "N"
        skip_keys = {"URL", "Title of Site", "Title", "Agency", "Office"}

        for col_key, col_letter in column_map.items():
            if col_key in skip_keys:
                continue
            if col_key == "Claimed":
                if write_claimed:
                    requests.append({
                        "range": f"{sheet_name}!{col_letter}{row_number}",
                        "values": [[username]],
                    })
            elif col_key == "Data Added":
                requests.append({
                    "range": f"{sheet_name}!{col_letter}{row_number}",
                    "values": [["N"]],
                })
            elif col_key == "Dataset Download Possible?":
                requests.append({
                    "range": f"{sheet_name}!{col_letter}{row_number}",
                    "values": [[download_possible]],
                })
            elif col_key == "Nominated to EOT / USGWDA":
                requests.append({
                    "range": f"{sheet_name}!{col_letter}{row_number}",
                    "values": [["N"]],
                })
            elif col_key == "Notes":
                requests.append({
                    "range": f"{sheet_name}!{col_letter}{row_number}",
                    "values": [[notes_value]],
                })

        if "Notes" not in column_map and service and sheet_id:
            notes_col_letter = self._get_next_column_letter(service, sheet_id, sheet_name)
            requests.append({
                "range": f"{sheet_name}!{notes_col_letter}1",
                "values": [["Notes"]],
            })
            requests.append({
                "range": f"{sheet_name}!{notes_col_letter}{row_number}",
                "values": [[notes_value]],
            })

        return requests

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
        """Build list of range/value update dicts for batchUpdate."""
        requests: List[Dict[str, Any]] = []

        new_url = (source_url_for_new_row or "").strip()
        if new_url and column_map.get("URL"):
            requests.append({
                "range": f"{sheet_name}!{column_map['URL']}{row_number}",
                "values": [[new_url]],
            })

        def _add(col_key: str, value: str) -> None:
            col_letter = column_map.get(col_key)
            if col_letter and value:
                requests.append({
                    "range": f"{sheet_name}!{col_letter}{row_number}",
                    "values": [[value]],
                })

        self._append_metadata_requests(
            requests,
            sheet_name,
            row_number,
            column_map,
            title_to_write,
            agency_to_write,
            office_to_write,
            use_add=_add,
        )

        if column_map.get("Claimed"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Claimed']}{row_number}",
                "values": [[username]],
            })
        if column_map.get("Data Added"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Data Added']}{row_number}",
                "values": [["Y"]],
            })
        if column_map.get("Dataset Download Possible?"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Dataset Download Possible?']}{row_number}",
                "values": [["Y"]],
            })
        if column_map.get("Nominated to EOT / USGWDA"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Nominated to EOT / USGWDA']}{row_number}",
                "values": [["Y"]],
            })

        download_date = (project.get("download_date") or "").strip()
        _add("Date Downloaded", download_date)

        if column_map.get("Download Location") and workspace_id:
            download_location = DOWNLOAD_LOCATION_TEMPLATE.format(
                workspace_id=workspace_id,
                version=(version or "V1").strip() or "V1",
            )
            requests.append({
                "range": f"{sheet_name}!{column_map['Download Location']}{row_number}",
                "values": [[download_location]],
            })

        file_size_raw = (project.get("file_size") or "").strip()
        if file_size_raw:
            try:
                file_size_display = format_file_size(int(float(file_size_raw)))
            except (ValueError, TypeError):
                file_size_display = file_size_raw
            _add("Dataset Size", file_size_display)

        extensions = (project.get("extensions") or "").strip()
        _add("File extensions of data uploads", extensions)

        if column_map.get("Metadata availability info"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Metadata availability info']}{row_number}",
                "values": [["Y"]],
            })

        return requests

    def _append_metadata_requests(
        self,
        requests: List[Dict[str, Any]],
        sheet_name: str,
        row_number: int,
        column_map: Dict[str, str],
        title_to_write: str,
        agency_to_write: str,
        office_to_write: str,
        *,
        use_add: Any | None = None,
    ) -> None:
        """Append title/agency/office cells using ``use_add`` or direct request list."""
        def _write(col_key: str, value: str) -> None:
            if use_add is not None:
                use_add(col_key, value)
                return
            col_letter = column_map.get(col_key)
            val = (value or "").strip()
            if col_letter and val:
                requests.append({
                    "range": f"{sheet_name}!{col_letter}{row_number}",
                    "values": [[val]],
                })

        title = normalize_inventory_title(title_to_write)
        if title and column_map.get("Title of Site"):
            _write("Title of Site", title)
        elif title and column_map.get("Title"):
            _write("Title", title)
        agency = (agency_to_write or "").strip()
        if agency and column_map.get("Agency"):
            _write("Agency", agency)
        office = (office_to_write or "").strip()
        if office and column_map.get("Office"):
            _write("Office", office)
