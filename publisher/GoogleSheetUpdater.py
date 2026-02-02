"""
Google Sheet updater for publisher module.

Updates a Google Sheet (e.g. master inventory) with publishing results by finding
the row via source_url match and writing Claimed, Data Added, Download Location, etc.
Logic derived from chiara_upload.update_google_sheet().
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.Logger import Logger

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    _GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    _GOOGLE_SHEETS_AVAILABLE = False
    HttpError = Exception  # type: ignore[misc, assignment]


# Required column names (case-insensitive / partial match in sheet header)
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

DOWNLOAD_LOCATION_TEMPLATE = "https://www.datalumos.org/datalumos/project/{workspace_id}/version/V1/view"


class GoogleSheetUpdater:
    """
    Updates a Google Sheet with publishing results for a project.

    Finds the row by matching source_url in the URL column, then writes
    Claimed, Data Added, Download Location, Date Downloaded, etc.
    """

    def update(
        self,
        sheet_id: str,
        credentials_path: Path,
        sheet_name: str,
        source_url: str,
        workspace_id: str,
        project: Dict[str, Any],
        username: str = "mkraley",
    ) -> tuple[bool, Optional[str]]:
        """
        Update the Google Sheet row matching source_url with publishing data.

        Args:
            sheet_id: Google Sheet ID (from URL).
            credentials_path: Path to service account credentials JSON.
            sheet_name: Worksheet/tab name.
            source_url: Source URL to match in the URL column.
            workspace_id: DataLumos workspace ID (for Download Location).
            project: Project dict (download_date, file_size, extensions).
            username: Value for "Claimed" column.

        Returns:
            (True, None) on success, (False, error_message) on failure.
        """
        if not _GOOGLE_SHEETS_AVAILABLE:
            return False, (
                "Google Sheets API not installed. "
                "Install with: pip install google-api-python-client google-auth google-auth-httplib2"
            )

        if not sheet_id or not credentials_path:
            return False, "Google Sheet ID and credentials path are required"

        if not source_url or not source_url.strip():
            return False, "Source URL is required to find matching row"

        try:
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path),
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            service = build("sheets", "v4", credentials=credentials)

            column_map = self._get_column_mapping(
                service, sheet_id, sheet_name, _REQUIRED_COLUMNS
            )
            if not column_map:
                return False, "Failed to get column mapping from Google Sheet"

            url_col_letter = column_map.get("URL")
            if not url_col_letter:
                return False, "Could not find URL column in sheet"

            row_number = self._find_row_by_url(
                service, sheet_id, sheet_name, url_col_letter, source_url.strip()
            )
            if not row_number:
                return False, f"Could not find row with matching URL: {source_url}"

            Logger.debug(f"Updating Google Sheet row {row_number}")

            update_requests = self._build_update_requests(
                sheet_name, row_number, column_map, workspace_id, project, username
            )
            if not update_requests:
                return False, "No data to update"

            body = {"valueInputOption": "USER_ENTERED", "data": update_requests}
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet_id,
                body=body,
            ).execute()

            Logger.info(
                f"Updated Google Sheet row {row_number} with {len(update_requests)} columns"
            )
            return True, None

        except ValueError:
            raise
        except FileNotFoundError as e:
            return False, f"Credentials file not found: {credentials_path}"
        except HttpError as e:
            return False, f"Google Sheets API error: {e}"
        except Exception as e:
            Logger.warning(f"Error updating Google Sheet: {e}")
            return False, str(e)

    def _column_index_to_letter(self, col_index: int) -> str:
        """Convert 1-based column index to letter (e.g. 1 -> A, 27 -> AA)."""
        result = ""
        while col_index > 0:
            col_index -= 1
            result = chr(65 + (col_index % 26)) + result
            col_index //= 26
        return result

    def _get_column_mapping(
        self,
        service: Any,
        sheet_id: str,
        sheet_name: str,
        required_columns: List[str],
    ) -> Optional[Dict[str, str]]:
        """Read header row and map column names to letters; require required_columns."""
        range_name = f"{sheet_name}!1:1"
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        if not values:
            return None

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
        return found_columns

    def _find_row_by_url(
        self,
        service: Any,
        sheet_id: str,
        sheet_name: str,
        url_column_letter: str,
        source_url: str,
    ) -> Optional[int]:
        """Return 1-based row number where URL column matches source_url, or None."""
        range_name = f"{sheet_name}!{url_column_letter}2:{url_column_letter}"
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        source_clean = source_url.strip().lower()

        for idx, row in enumerate(values):
            if row and len(row) > 0:
                cell_url = str(row[0]).strip().lower()
                if (
                    source_clean == cell_url
                    or source_clean in cell_url
                    or cell_url in source_clean
                ):
                    return idx + 2
        return None

    def _build_update_requests(
        self,
        sheet_name: str,
        row_number: int,
        column_map: Dict[str, str],
        workspace_id: str,
        project: Dict[str, Any],
        username: str,
    ) -> List[Dict[str, Any]]:
        """Build list of range/value update dicts for batchUpdate."""
        requests: List[Dict[str, Any]] = []

        def _add(col_key: str, value: str) -> None:
            col_letter = column_map.get(col_key)
            if col_letter and value:
                requests.append({
                    "range": f"{sheet_name}!{col_letter}{row_number}",
                    "values": [[value]],
                })

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
                workspace_id=workspace_id
            )
            requests.append({
                "range": f"{sheet_name}!{column_map['Download Location']}{row_number}",
                "values": [[download_location]],
            })

        file_size = (project.get("file_size") or "").strip()
        _add("Dataset Size", file_size)

        extensions = (project.get("extensions") or "").strip()
        _add("File extensions of data uploads", extensions)

        if column_map.get("Metadata availability info"):
            requests.append({
                "range": f"{sheet_name}!{column_map['Metadata availability info']}{row_number}",
                "values": [["Y"]],
            })

        return requests
