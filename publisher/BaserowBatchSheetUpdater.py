"""
Google Sheet updater for the Baserow batch import template format.

Writes columns aligned with the DRP Baserow batch import spreadsheet (see the Mapping
tab on the template workbook). Row matching is still by exact source URL.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.Args import Args
from utils.baserow_sheet_utils import (
    baserow_contact_value,
    baserow_organization,
    format_baserow_backup_title,
    format_baserow_dataset_title,
    format_baserow_file_extensions,
    format_dataset_size_gb_jedec,
    website_from_source_url,
)
from utils.title_utils import normalize_inventory_title

from publisher.inventory_sheet_updater_base import (
    DOWNLOAD_LOCATION_TEMPLATE,
    InventorySheetUpdaterBase,
)

_REQUIRED_COLUMNS = [
    "URL",
    "Title for Datasets table",
    "Title for Backups table",
    "Organization",
    "Agency",
    "Websites",
    "Date downloaded",
    "Download Location",
    "Dataset size",
    "File extensions",
    "Maintainers",
]

_OPTIONAL_COLUMNS = [
    "Metadata available",
    "Metadata URL",
    "Notes",
    "Notes for Datasets Table",
    "Nominated to EOT",
    "Contact",
    "Admin notes",
]


class BaserowBatchSheetUpdater(InventorySheetUpdaterBase):
    """
    Updates the Baserow batch import Google Sheet with publishing results.

    Maps project metadata and DataLumos publish outcomes to the batch-import column
    layout (titles, organization, websites, GB size, comma-separated extensions, etc.).
    """

    def _required_columns_publish(self) -> List[str]:
        return list(_REQUIRED_COLUMNS)

    def _optional_columns_publish(self) -> List[str]:
        return list(_OPTIONAL_COLUMNS)

    def _required_columns_sheet_only(self, *, write_claimed: bool) -> List[str]:
        required = ["URL"]
        if write_claimed:
            required.append("Contact")
        return required

    def _optional_columns_sheet_only(self) -> List[str]:
        return [
            "Notes",
            "Notes for Datasets Table",
            "Title for Datasets table",
            "Title for Backups table",
            "Organization",
            "Agency",
            "Websites",
            "Admin notes",
            "Contact",
        ]

    def _required_columns_claimed(self) -> List[str]:
        return ["URL", "Contact"]

    def _optional_columns_claimed(self) -> List[str]:
        return [
            "Title for Datasets table",
            "Title for Backups table",
            "Organization",
            "Agency",
            "Websites",
        ]

    def _contact_value(self) -> str:
        """Return the configured Baserow Contact column value."""
        return baserow_contact_value(
            baserow_contact=getattr(Args, "baserow_contact", None),
            google_username=getattr(Args, "google_username", None),
        )

    def _metadata_available_value(self) -> str:
        """Return ``yes`` or ``no`` for the Metadata available column on publish."""
        if getattr(Args, "default_metadata_available", True):
            return "yes"
        return "no"

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
            "Title for Datasets table",
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
            "Organization",
            "office",
        )
        if not office and project:
            org_from_agency = self._metadata_value_if_cell_empty(
                service,
                sheet_id,
                sheet_name,
                row_number,
                append_new,
                column_map,
                project,
                "Organization",
                "agency",
            )
            if org_from_agency:
                office = org_from_agency
        return title or "", agency or "", office or ""

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
        """Build batchUpdate cells for a successful publish on the Baserow template."""
        requests: List[Dict[str, Any]] = []

        source_url = (source_url_for_new_row or "").strip()
        if not source_url:
            source_url = (project.get("source_url") or "").strip()

        if source_url_for_new_row and column_map.get("URL"):
            requests.append({
                "range": f"{sheet_name}!{column_map['URL']}{row_number}",
                "values": [[source_url_for_new_row.strip()]],
            })

        self._append_baserow_metadata_requests(
            requests,
            sheet_name,
            row_number,
            column_map,
            source_url,
            title_to_write,
            agency_to_write,
            office_to_write,
        )

        if column_map.get("Contact"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Contact']}{row_number}",
                "values": [[self._contact_value()]],
            })

        download_date = (project.get("download_date") or "").strip()
        self._append_cell(requests, sheet_name, row_number, column_map, "Date downloaded", download_date)

        if column_map.get("Download Location") and workspace_id:
            download_location = DOWNLOAD_LOCATION_TEMPLATE.format(
                workspace_id=workspace_id,
                version=(version or "V1").strip() or "V1",
            )
            requests.append({
                "range": f"{sheet_name}!{column_map['Download Location']}{row_number}",
                "values": [[download_location]],
            })

        size_gb = format_dataset_size_gb_jedec(project.get("file_size"))
        self._append_cell(requests, sheet_name, row_number, column_map, "Dataset size", size_gb)

        extensions = format_baserow_file_extensions((project.get("extensions") or "").strip())
        self._append_cell(requests, sheet_name, row_number, column_map, "File extensions", extensions)

        maintainers = (getattr(Args, "baserow_maintainers", None) or "DRP,DL").strip()
        self._append_cell(requests, sheet_name, row_number, column_map, "Maintainers", maintainers)

        if column_map.get("Metadata available"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Metadata available']}{row_number}",
                "values": [[self._metadata_available_value()]],
            })

        if column_map.get("Nominated to EOT"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Nominated to EOT']}{row_number}",
                "values": [["yes"]],
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
        """Build batchUpdate cells for sheet-only statuses on the Baserow template."""
        del dataset_download_possible  # Not used in Baserow format.
        requests: List[Dict[str, Any]] = []

        url = (source_url or "").strip()
        if append_new_row and url and column_map.get("URL"):
            requests.append({
                "range": f"{sheet_name}!{column_map['URL']}{row_number}",
                "values": [[url]],
            })

        self._append_baserow_metadata_requests(
            requests,
            sheet_name,
            row_number,
            column_map,
            url,
            title_to_write,
            agency_to_write,
            office_to_write,
        )

        if column_map.get("Notes"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Notes']}{row_number}",
                "values": [[notes_value]],
            })
        elif service and sheet_id:
            notes_col_letter = self._get_next_column_letter(service, sheet_id, sheet_name)
            requests.append({
                "range": f"{sheet_name}!{notes_col_letter}1",
                "values": [["Notes"]],
            })
            requests.append({
                "range": f"{sheet_name}!{notes_col_letter}{row_number}",
                "values": [[notes_value]],
            })

        if write_claimed and column_map.get("Contact"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Contact']}{row_number}",
                "values": [[self._contact_value()]],
            })

        return requests

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
        """Build batchUpdate cells that set Contact (plus URL/metadata on append)."""
        requests: List[Dict[str, Any]] = []

        url = (source_url or "").strip()
        if append_new_row and url and column_map.get("URL"):
            requests.append({
                "range": f"{sheet_name}!{column_map['URL']}{row_number}",
                "values": [[url]],
            })

        self._append_baserow_metadata_requests(
            requests,
            sheet_name,
            row_number,
            column_map,
            url,
            title_to_write,
            agency_to_write,
            office_to_write,
        )

        if column_map.get("Contact"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Contact']}{row_number}",
                "values": [[self._contact_value()]],
            })
        return requests

    def _append_baserow_metadata_requests(
        self,
        requests: List[Dict[str, Any]],
        sheet_name: str,
        row_number: int,
        column_map: Dict[str, str],
        source_url: str,
        title_to_write: str,
        agency_to_write: str,
        office_to_write: str,
    ) -> None:
        """Append title, organization, agency, and website cells for Baserow format."""
        title, truncation_note = format_baserow_dataset_title(title_to_write)
        if title:
            self._append_cell(
                requests,
                sheet_name,
                row_number,
                column_map,
                "Title for Datasets table",
                title,
            )
            backup_title = format_baserow_backup_title(title)
            self._append_cell(
                requests,
                sheet_name,
                row_number,
                column_map,
                "Title for Backups table",
                backup_title,
            )
            self._append_cell(
                requests,
                sheet_name,
                row_number,
                column_map,
                "Notes for Datasets Table",
                truncation_note,
            )

        agency = (agency_to_write or "").strip()
        organization = baserow_organization(agency, office_to_write)
        self._append_cell(requests, sheet_name, row_number, column_map, "Agency", agency)
        self._append_cell(
            requests,
            sheet_name,
            row_number,
            column_map,
            "Organization",
            organization,
        )

        website = website_from_source_url(source_url)
        self._append_cell(requests, sheet_name, row_number, column_map, "Websites", website)

    def _append_cell(
        self,
        requests: List[Dict[str, Any]],
        sheet_name: str,
        row_number: int,
        column_map: Dict[str, str],
        col_key: str,
        value: str,
    ) -> None:
        """Append one cell update when ``value`` and the mapped column are present."""
        col_letter = column_map.get(col_key)
        val = (value or "").strip()
        if col_letter and val:
            requests.append({
                "range": f"{sheet_name}!{col_letter}{row_number}",
                "values": [[val]],
            })
