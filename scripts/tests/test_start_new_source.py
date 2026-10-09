"""Tests for creating a new pipeline source."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from scripts.new_source_google import add_inventory_tab
from scripts.new_source_setup import build_source_config, normalize_source_code
from scripts.new_source_sheet import (
    HEADER_TEMPLATE_TAB,
    INVENTORY_SPREADSHEET_ID,
    assert_tab_available,
    find_data_tab,
    header_values_range,
)
from scripts.start_new_source import run


def _config(root: Path) -> dict[str, Any]:
    """Return a minimal config that uses ``root`` for the template output folder."""
    return {
        "source": "nps",
        "gwda_email": "mike@kraley.com",
        "google_credentials": "missing-creds.json",
        "sources": {
            "nps": {
                "base_output_dir": str(root / "NPSData"),
                "google_sheet_name": "NPS",
                "datalumos_username": "mkraley+nps@gmail.com",
                "datalumos_password": "secret",
                "google_sheet_id": "template-sheet",
                "baserow_contact": "mike@kraley.com",
                "nps_collection_id": 9688,
            }
        },
    }


class TestNewSourcePlan(unittest.TestCase):
    """Tests for source-code planning that does not call Google."""

    def test_normalize_source_code(self) -> None:
        """Initials are stored as lowercase letters."""
        self.assertEqual(normalize_source_code(" NRC "), "nrc")
        with self.assertRaises(ValueError):
            normalize_source_code("n1")

    def test_build_source_config_drops_template_secrets(self) -> None:
        """The new section keeps Baserow defaults and a blank DataLumos password."""
        template = _config(Path(r"C:\DataRescue"))["sources"]["nps"]
        section = build_source_config("nrc", template, "new-id", "mike@kraley.com")
        self.assertEqual(section["google_sheet_name"], "NRC")
        self.assertEqual(section["google_sheet_id"], "new-id")
        self.assertEqual(section["datalumos_username"], "mkraley+nrc@gmail.com")
        self.assertEqual(section["datalumos_password"], "")
        self.assertEqual(section["inventory_sheet_format"], "baserow_batch")
        self.assertNotIn("nps_collection_id", section)
        self.assertTrue(section["base_output_dir"].endswith("NRCData"))

    def test_find_data_tab_reports_available_tabs(self) -> None:
        """A missing template tab lists the worksheets that were found."""
        with self.assertRaises(ValueError) as raised:
            find_data_tab([{"title": "Mapping", "sheetId": 1}], "NPS")
        self.assertIn("Mapping", str(raised.exception))

    def test_header_values_range_quotes_tab_name(self) -> None:
        """The header range is row 1 and the tab name is quoted."""
        self.assertEqual(header_values_range("O'Brien"), "'O''Brien'!1:1")

    def test_assert_tab_available_rejects_existing_name(self) -> None:
        """A tab that already exists is not created again."""
        with self.assertRaises(ValueError):
            assert_tab_available([{"title": "nrc"}], "NRC")


class TestStartNewSourceCommand(unittest.TestCase):
    """Tests for the start-new-source command."""

    def test_script_file_can_be_launched(self) -> None:
        """Running the file directly can import sibling modules."""
        script = Path(__file__).resolve().parents[1] / "start_new_source.py"
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=script.parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("initials", result.stdout)
        self.assertNotIn("sheet-url", result.stdout)

    def test_dry_run_leaves_config_unchanged(self) -> None:
        """Dry run prints the plan and does not write a database or config entry."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(_config(root)), encoding="utf-8")
            code = run(["nrc", "--config", str(config_path), "--dry-run"])
            self.assertEqual(code, 0)
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("nrc", saved["sources"])
            self.assertFalse((root / "nrc.db").exists())

    @patch("scripts.start_new_source.google_sheets_client")
    @patch("scripts.start_new_source.add_inventory_tab")
    def test_run_creates_source(
        self,
        mock_add_tab: MagicMock,
        mock_clients: MagicMock,
    ) -> None:
        """A live run adds a tab on the shared spreadsheet and switches source."""
        mock_add_tab.return_value = (
            f"https://docs.google.com/spreadsheets/d/{INVENTORY_SPREADSHEET_ID}/edit#gid=9"
        )
        mock_clients.return_value = MagicMock()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(_config(root)), encoding="utf-8")
            code = run(["NRC", "--config", str(config_path)])
            self.assertEqual(code, 0)
            saved = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["source"], "nrc")
            section = saved["sources"]["nrc"]
            self.assertEqual(section["google_sheet_id"], INVENTORY_SPREADSHEET_ID)
            self.assertEqual(section["datalumos_password"], "")
            self.assertTrue((root / "NRCData").is_dir())
            connection = sqlite3.connect(root / "nrc.db")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            connection.close()
            self.assertIn("projects", tables)
            self.assertNotIn("nps_projects", tables)
            self.assertNotIn("nps_products", tables)
        self.assertEqual(mock_add_tab.call_args.args[1], INVENTORY_SPREADSHEET_ID)
        self.assertEqual(mock_add_tab.call_args.args[2], HEADER_TEMPLATE_TAB)
        self.assertEqual(mock_add_tab.call_args.args[3], "NRC")

    def test_add_inventory_tab_copies_header_only(self) -> None:
        """A new tab is added and receives only the template header row."""
        sheets = MagicMock()
        sheets.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [
                {"properties": {"title": "NPS", "sheetId": 7}},
                {"properties": {"title": "Mapping", "sheetId": 8}},
            ],
        }
        values = sheets.spreadsheets.return_value.values.return_value
        values.get.return_value.execute.return_value = {"values": [["Title", "URL"]]}
        sheets.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {
            "replies": [{"addSheet": {"properties": {"sheetId": 99, "title": "NRC"}}}]
        }
        link = add_inventory_tab(sheets, "abc", "NPS", "NRC")
        self.assertEqual(link, "https://docs.google.com/spreadsheets/d/abc/edit#gid=99")
        added = sheets.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"]
        self.assertEqual(
            added["requests"],
            [{"addSheet": {"properties": {"title": "NRC"}}}],
        )
        written = values.update.call_args.kwargs
        self.assertEqual(written["range"], "'NRC'!1:1")
        self.assertEqual(written["body"], {"values": [["Title", "URL"]]})

    def test_add_inventory_tab_names_sheet_id_when_add_fails(self) -> None:
        """A failed add still reports the spreadsheet id."""
        sheets = MagicMock()
        sheets.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [{"properties": {"title": "NPS", "sheetId": 7}}],
        }
        values = sheets.spreadsheets.return_value.values.return_value
        values.get.return_value.execute.return_value = {"values": [["Title"]]}
        sheets.spreadsheets.return_value.batchUpdate.return_value.execute.side_effect = RuntimeError(
            "add failed"
        )
        with self.assertRaises(RuntimeError) as raised:
            add_inventory_tab(sheets, "abc", "NPS", "NRC")
        self.assertIn("abc", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
