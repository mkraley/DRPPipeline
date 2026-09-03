"""
Unit tests for BaserowBatchSheetUpdater.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from publisher.BaserowBatchSheetUpdater import BaserowBatchSheetUpdater
from publisher.inventory_sheet_updater_base import DOWNLOAD_LOCATION_TEMPLATE

import publisher.inventory_sheet_updater_base as _base_module

_GOOGLE_AVAILABLE = getattr(_base_module, "GOOGLE_SHEETS_AVAILABLE", False)
skip_if_no_google = unittest.skipIf(not _GOOGLE_AVAILABLE, "Google Sheets API not installed")


class TestBaserowBatchSheetUpdater(unittest.TestCase):
    """Tests for Baserow batch import sheet updates."""

    def setUp(self) -> None:
        """Initialize Args and Logger."""
        sys.argv = ["test", "publisher"]
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Args._config.update({
            "baserow_maintainers": "DRP,DL",
            "baserow_contact": "mike@kraley.com",
            "default_metadata_available": True,
        })
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Reset Args."""
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}

    def test_build_update_requests_uses_gb_and_baserow_fields(self) -> None:
        """Publish update writes Baserow columns with GB size and yes literals."""
        updater = BaserowBatchSheetUpdater()
        column_map = {
            "URL": "A",
            "Title for Datasets table": "B",
            "Title for Backups table": "C",
            "Organization": "D",
            "Agency": "E",
            "Websites": "F",
            "Date downloaded": "G",
            "Download Location": "H",
            "Dataset size": "I",
            "File extensions": "J",
            "Maintainers": "K",
            "Metadata available": "L",
            "Nominated to EOT": "M",
            "Contact": "N",
        }
        project = {
            "source_url": "https://rosap.ntl.bts.gov/view/dot/54854",
            "download_date": "2025-01-15",
            "file_size": str(1024**3),
            "extensions": "csv, zip",
        }
        requests = updater._build_update_requests(
            "BTS",
            2,
            column_map,
            "239181",
            project,
            "mkraley",
            title_to_write="Dataset Title",
            agency_to_write="DOT",
            office_to_write="BTS",
            version="V1",
        )
        values_by_col = {}
        for req in requests:
            letter = req["range"].split("!")[1][0]
            values_by_col[letter] = req["values"][0][0]

        self.assertEqual(values_by_col["B"], "Dataset Title")
        self.assertEqual(values_by_col["C"], "Dataset Title")
        self.assertEqual(values_by_col["D"], "BTS")
        self.assertEqual(values_by_col["E"], "DOT")
        self.assertEqual(values_by_col["F"], "rosap.ntl.bts.gov")
        self.assertEqual(values_by_col["G"], "2025-01-15")
        self.assertEqual(
            values_by_col["H"],
            DOWNLOAD_LOCATION_TEMPLATE.format(workspace_id="239181", version="V1"),
        )
        self.assertEqual(values_by_col["I"], "1.0")
        self.assertEqual(values_by_col["J"], "CSV,ZIP")
        self.assertEqual(values_by_col["K"], "DRP,DL")
        self.assertEqual(values_by_col["L"], "yes")
        self.assertEqual(values_by_col["M"], "yes")
        self.assertEqual(values_by_col["N"], "mike@kraley.com")

    def test_build_update_requests_writes_no_metadata_when_disabled(self) -> None:
        """Metadata available is no when default_metadata_available is False."""
        Args._config["default_metadata_available"] = False
        updater = BaserowBatchSheetUpdater()
        column_map = {
            "Metadata available": "L",
            "Contact": "N",
            "Dataset size": "I",
        }
        project = {"source_url": "https://example.com/x", "file_size": str(1024**3)}
        requests = updater._build_update_requests(
            "BTS", 2, column_map, "1", project, "mkraley"
        )
        metadata_writes = [
            r for r in requests if "L2" in r.get("range", "")
        ]
        self.assertEqual(metadata_writes[0]["values"], [["no"]])

    def test_build_sheet_only_requests_writes_notes(self) -> None:
        """Sheet-only paths write Notes like the data inventories updater."""
        updater = BaserowBatchSheetUpdater()
        column_map = {"URL": "A", "Notes": "B", "Contact": "C"}
        requests = updater._build_sheet_only_requests(
            "BTS",
            2,
            column_map,
            append_new_row=True,
            source_url="https://example.com/x",
            notes_value="needs scripting",
            write_claimed=False,
        )
        notes = [r for r in requests if r.get("values") == [["needs scripting"]]]
        self.assertEqual(len(notes), 1)
        self.assertIn("B2", notes[0]["range"])
        contact_writes = [r for r in requests if r.get("values") == [["mike@kraley.com"]]]
        self.assertEqual(contact_writes, [])

    def test_build_update_requests_quotes_backup_title(self) -> None:
        """Backup title column quotes titles with commas; dataset title is unquoted."""
        updater = BaserowBatchSheetUpdater()
        column_map = {
            "Title for Datasets table": "B",
            "Title for Backups table": "C",
        }
        project = {"source_url": "https://example.com/x", "file_size": "1"}
        requests = updater._build_update_requests(
            "BTS",
            2,
            column_map,
            "1",
            project,
            "u",
            title_to_write="Part A, Part B",
        )
        values_by_col = {}
        for req in requests:
            letter = req["range"].split("!")[1][0]
            values_by_col[letter] = req["values"][0][0]
        self.assertEqual(values_by_col["B"], "Part A, Part B")
        self.assertEqual(values_by_col["C"], '"Part A, Part B"')

    def test_build_update_requests_replaces_title_colons(self) -> None:
        """Dataset titles replace colon-space with an em dash."""
        updater = BaserowBatchSheetUpdater()
        column_map = {
            "Title for Datasets table": "B",
            "Title for Backups table": "C",
        }
        project = {"source_url": "https://example.com/x", "file_size": "1"}
        requests = updater._build_update_requests(
            "BTS",
            2,
            column_map,
            "1",
            project,
            "u",
            title_to_write="National Transportation Atlas Databases: 2003",
        )
        values_by_col = {}
        for req in requests:
            letter = req["range"].split("!")[1][0]
            values_by_col[letter] = req["values"][0][0]
        expected = "National Transportation Atlas Databases — 2003"
        self.assertEqual(values_by_col["B"], expected)
        self.assertEqual(values_by_col["C"], expected)

    def test_build_update_requests_writes_truncation_note(self) -> None:
        """Over-length titles write the original into Notes for Datasets Table."""
        updater = BaserowBatchSheetUpdater()
        column_map = {
            "Title for Datasets table": "B",
            "Notes for Datasets Table": "Z",
        }
        long_title = ("Word " * 60).strip()
        project = {"source_url": "https://example.com/x", "file_size": "1"}
        requests = updater._build_update_requests(
            "BTS",
            2,
            column_map,
            "1",
            project,
            "u",
            title_to_write=long_title,
        )
        notes = [r for r in requests if "Z2" in r.get("range", "")]
        self.assertEqual(len(notes), 1)
        self.assertIn(long_title, notes[0]["values"][0][0])

    @skip_if_no_google
    @patch("publisher.inventory_sheet_updater_base.build_sheets_v4_service")
    @patch("google.oauth2.service_account.Credentials.from_service_account_file")
    def test_update_success_mocked(
        self, mock_from_sa: MagicMock, mock_build: MagicMock
    ) -> None:
        """Successful update maps Baserow template headers with (required) suffix."""
        mock_creds = MagicMock()
        mock_creds.universe_domain = "googleapis.com"
        mock_from_sa.return_value = mock_creds
        mock_service = MagicMock()

        header_response = {
            "values": [[
                "Title for Datasets table (required)",
                "Title for Backups table (required)",
                "Organization (required)",
                "Agency (required)",
                "URL (required)",
                "Websites (required)",
                "Date downloaded (required)",
                "Download Location (required)",
                "Dataset size (required)",
                "File extensions (required)",
                "Maintainers (required)",
                "Metadata available (optional)",
                "Nominated to EOT (optional)",
                "Contact (optional)",
            ]]
        }
        url_column_response = {"values": []}
        mock_get = mock_service.spreadsheets.return_value.values.return_value.get.return_value
        mock_get.execute.side_effect = [header_response, url_column_response, url_column_response]
        mock_service.spreadsheets.return_value.values.return_value.batchUpdate.return_value.execute.return_value = {}
        mock_build.return_value = mock_service

        cred_path = Path(tempfile.gettempdir()) / "creds_baserow_test.json"
        cred_path.write_text("{}")

        updater = BaserowBatchSheetUpdater()
        with patch.object(Args, "google_sheet_id", "sheet123"), patch.object(
            Args, "google_credentials", cred_path
        ), patch.object(Args, "google_sheet_name", "BTS"), patch.object(
            Args, "google_username", "mkraley"
        ):
            success, msg = updater.update(
                "https://rosap.ntl.bts.gov/view/dot/99999",
                "239181",
                {
                    "source_url": "https://rosap.ntl.bts.gov/view/dot/54854",
                    "title": "Test Dataset",
                    "agency": "DOT",
                    "office": "BTS",
                    "download_date": "2025-01-15",
                    "file_size": str(2 * 1024**3),
                    "extensions": "csv",
                },
            )

        cred_path.unlink(missing_ok=True)
        self.assertTrue(success)
        self.assertIsNone(msg)
        mock_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_called_once()
