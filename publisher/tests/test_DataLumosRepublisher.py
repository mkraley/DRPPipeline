"""
Unit tests for DataLumosRepublisher.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage import Storage
from utils.Args import Args
from utils.Logger import Logger
from verify.DatalumosViewFileStats import DatalumosViewFileStats
from publisher.DataLumosRepublisher import (
    REPUBLISH_STATUS_NOTE,
    REPUBLISH_VERSION,
    REPUBLISH_VERSION_TITLE,
    STATUS_UPDATED_INVENTORY,
    DataLumosRepublisher,
)


class TestDataLumosRepublisher(unittest.TestCase):
    """Tests for re-publish entry button, inventory gate, and finalize."""

    def setUp(self) -> None:
        """Initialize Args, Logger, and temp Storage."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "republisher"]
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.temp_dir / "test.db"
        self.storage = Storage.initialize("StorageSQLLite", db_path=self.test_db_path)
        self.module = DataLumosRepublisher()

    def tearDown(self) -> None:
        """Restore argv and reset Storage/Args."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        Args._initialized = False
        if self.temp_dir.exists():
            import shutil

            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_version_title_constant(self) -> None:
        """Version title text matches the product requirement."""
        self.assertEqual(REPUBLISH_VERSION_TITLE, "added missing file")

    def test_published_view_url_is_v2(self) -> None:
        """Republisher stores published_url pointing at version V2."""
        url = self.module._published_view_url("248873")
        self.assertEqual(
            url,
            "https://www.datalumos.org/datalumos/project/248873/version/V2/view",
        )
        self.assertEqual(self.module._sheet_download_version(), REPUBLISH_VERSION)

    def test_click_publish_entry_uses_republish_button(self) -> None:
        """Entry click targets Re-Publish Project, not Publish Project."""
        page = MagicMock()
        btn = MagicMock()
        page.locator.return_value = btn
        self.module._click_publish_entry_button(page)
        page.locator.assert_called_once_with(
            "button.btn-primary:has-text('Re-Publish Project')"
        )
        btn.click.assert_called_once()

    def test_prepare_review_page_fills_version_title(self) -> None:
        """Review page fills #versionTitle with the re-publish note."""
        page = MagicMock()
        version_input = MagicMock()
        page.locator.return_value = version_input
        self.module._wait_for_busy = MagicMock()  # type: ignore[method-assign]
        self.module._prepare_review_page(page)
        page.locator.assert_called_with("#versionTitle")
        version_input.wait_for.assert_called_once_with(
            state="visible", timeout=60000
        )
        version_input.fill.assert_called_once_with(REPUBLISH_VERSION_TITLE)

    def test_base_publisher_prepare_review_is_noop(self) -> None:
        """Regular publisher does not fill version title."""
        from publisher.DataLumosPublisher import DataLumosPublisher

        publisher = DataLumosPublisher()
        page = MagicMock()
        publisher._prepare_review_page(page)
        page.locator.assert_not_called()

    def test_pre_publish_gate_aborts_on_mismatch(self) -> None:
        """Inventory mismatch returns an abort error message."""
        self.module._workspace_inventory_mismatches = MagicMock(  # type: ignore[method-assign]
            return_value=["file count mismatch: database=5, datalumos=4"]
        )
        message = self.module._pre_publish_gate(
            MagicMock(),
            {"num_files": 5, "file_size": "1 MB"},
            7,
        )
        assert message is not None
        self.assertIn("Aborting republish", message)
        self.assertIn("file count mismatch", message)

    def test_pre_publish_gate_ok_when_matching(self) -> None:
        """Matching inventory allows republish to proceed."""
        self.module._workspace_inventory_mismatches = MagicMock(  # type: ignore[method-assign]
            return_value=[]
        )
        self.assertIsNone(
            self.module._pre_publish_gate(MagicMock(), {"num_files": 5}, 7)
        )

    def test_finalize_sets_updated_inventory_and_note(self) -> None:
        """Finalize writes updated_inventory and Republished status note."""
        drpid = Storage.create_record("https://example.gov/data")
        Storage.update_record(
            drpid, {"status": "published", "status_notes": "Prior note"}
        )
        self.module._finalize_after_publish(drpid)
        project = Storage.get(drpid)
        assert project is not None
        self.assertEqual(project["status"], STATUS_UPDATED_INVENTORY)
        self.assertIn("Prior note", project["status_notes"])
        self.assertIn(REPUBLISH_STATUS_NOTE, project["status_notes"])

    @patch.object(DataLumosRepublisher, "_update_google_sheet_if_configured")
    @patch.object(DataLumosRepublisher, "_publish_workspace", return_value=(True, None))
    @patch.object(
        DataLumosRepublisher, "_uploads_incomplete_on_project_page", return_value=None
    )
    @patch.object(DataLumosRepublisher, "_pre_publish_gate", return_value=None)
    def test_run_from_reuploaded_sets_updated_inventory(
        self,
        mock_gate: MagicMock,
        mock_ready: MagicMock,
        mock_publish: MagicMock,
        mock_sheet: MagicMock,
    ) -> None:
        """Successful republish ends at updated_inventory with V2 URL and note."""
        drpid = Storage.create_record("https://example.gov/data")
        Storage.update_record(
            drpid,
            {
                "status": "re-uploaded",
                "datalumos_id": "248873",
                "file_size": "346.1 MB",
                "num_files": 5,
            },
        )
        page = MagicMock()
        self.module._session = MagicMock()
        self.module._session.ensure_browser.return_value = page

        with patch(
            "upload.DataLumosAuthenticator.wait_for_human_verification"
        ):
            self.module.run(drpid)

        project = Storage.get(drpid)
        assert project is not None
        self.assertEqual(project["status"], STATUS_UPDATED_INVENTORY)
        self.assertEqual(
            project["published_url"],
            "https://www.datalumos.org/datalumos/project/248873/version/V2/view",
        )
        self.assertIn(REPUBLISH_STATUS_NOTE, project.get("status_notes") or "")
        mock_gate.assert_called_once()
        mock_publish.assert_called_once()
        mock_sheet.assert_called_once()

    @patch.object(DataLumosRepublisher, "_publish_workspace")
    @patch.object(
        DataLumosRepublisher,
        "_pre_publish_gate",
        return_value="Aborting republish: mismatch",
    )
    def test_run_aborts_when_inventory_gate_fails(
        self,
        mock_gate: MagicMock,
        mock_publish: MagicMock,
    ) -> None:
        """Gate failure records errors and does not republish or finalize."""
        drpid = Storage.create_record("https://example.gov/data")
        Storage.update_record(
            drpid,
            {
                "status": "re-uploaded",
                "datalumos_id": "248873",
                "num_files": 5,
                "file_size": "1 MB",
            },
        )
        page = MagicMock()
        self.module._session = MagicMock()
        self.module._session.ensure_browser.return_value = page
        self.module._finalize_after_publish = MagicMock()  # type: ignore[method-assign]
        self.module._update_google_sheet_if_configured = MagicMock()  # type: ignore[method-assign]

        with patch(
            "upload.DataLumosAuthenticator.wait_for_human_verification"
        ):
            self.module.run(drpid)

        mock_publish.assert_not_called()
        self.module._finalize_after_publish.assert_not_called()
        self.module._update_google_sheet_if_configured.assert_not_called()
        project = Storage.get(drpid)
        assert project is not None
        self.assertEqual(project["status"], "re-uploaded-error")
        self.assertIn("Aborting republish", project.get("errors") or "")

    @patch("publisher.DataLumosRepublisher.workspace_file_stats_from_page")
    def test_workspace_inventory_mismatches_uses_verify_counts(
        self,
        mock_stats: MagicMock,
    ) -> None:
        """Workspace inventory check compares scraped stats to the database."""
        mock_stats.return_value = DatalumosViewFileStats(
            file_count=4, total_bytes=1000
        )
        errors = self.module._workspace_inventory_mismatches(
            MagicMock(),
            {"num_files": 5, "file_size": "1000"},
        )
        self.assertTrue(any("inventory mismatch" in e for e in errors))
        self.assertTrue(any("files=5/4" in e for e in errors))
        mock_stats.assert_called_once()

    def test_workspace_file_stats_from_page_parses_table(self) -> None:
        """Workspace scraper reads name/size from table.table-hover columns."""
        from publisher.DataLumosRepublisher import workspace_file_stats_from_page

        page = MagicMock()
        page.evaluate.return_value = {
            "files": [
                {"name": "a.pdf", "size": "1.0 KB"},
                {"name": "b.zip", "size": "1.0 KB"},
            ]
        }
        stats = workspace_file_stats_from_page(page)
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 2)
        self.assertEqual(stats.total_bytes, 2048)
        self.assertEqual(stats.file_names, ("a.pdf", "b.zip"))

    def test_workspace_file_stats_from_page_no_rows(self) -> None:
        """Empty workspace table surfaces no_files_found."""
        from publisher.DataLumosRepublisher import workspace_file_stats_from_page

        page = MagicMock()
        page.evaluate.return_value = {"error": "no_files_found"}
        stats = workspace_file_stats_from_page(page)
        self.assertEqual(stats.error, "no_files_found")


if __name__ == "__main__":
    unittest.main()
