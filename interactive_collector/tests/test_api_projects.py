"""Tests for interactive_collector.api_projects."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from interactive_collector.api_projects import (
    STATUS_EXTERNAL_ARCHIVE,
    STATUS_SOURCED,
    ensure_output_folder,
    get_first_eligible,
    get_interactive_prereq,
    get_next_eligible_after,
)
from interactive_collector.collector_state import get_result_by_drpid
from utils.Args import Args
from utils.Logger import Logger


class TestEnsureOutputFolder(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        get_result_by_drpid().clear()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        get_result_by_drpid().clear()

    @patch("interactive_collector.api_projects.get_base_output_dir")
    def test_recreate_true_removes_existing_files(self, mock_base: unittest.mock.Mock) -> None:
        mock_base.return_value = self.tmpdir
        folder = self.tmpdir / "DRP000007"
        folder.mkdir(parents=True)
        marker = folder / "keep.txt"
        marker.write_text("gone", encoding="utf-8")

        path = ensure_output_folder(7, recreate=True)
        self.assertEqual(path, str(folder))
        self.assertTrue(folder.is_dir())
        self.assertFalse(marker.exists())

    @patch("interactive_collector.api_projects.get_base_output_dir")
    def test_recreate_false_preserves_existing_files(self, mock_base: unittest.mock.Mock) -> None:
        mock_base.return_value = self.tmpdir
        folder = self.tmpdir / "DRP000008"
        folder.mkdir(parents=True)
        marker = folder / "keep.txt"
        marker.write_text("stay", encoding="utf-8")

        path = ensure_output_folder(8, recreate=False)
        self.assertEqual(path, str(folder))
        self.assertTrue(marker.exists())
        self.assertEqual(marker.read_text(encoding="utf-8"), "stay")

    @patch("interactive_collector.api_projects.get_base_output_dir")
    def test_default_resolve_preserves_existing_files(self, mock_base: unittest.mock.Mock) -> None:
        """Fallback ensure_output_folder() must not wipe when recreate is omitted."""
        mock_base.return_value = self.tmpdir
        folder = self.tmpdir / "DRP000010"
        folder.mkdir(parents=True)
        marker = folder / "keep.txt"
        marker.write_text("stay", encoding="utf-8")

        path = ensure_output_folder(10)
        self.assertEqual(path, str(folder))
        self.assertTrue(marker.exists())

    @patch("interactive_collector.api_projects._ensure_storage")
    def test_recreate_false_uses_storage_folder_path(
        self,
        _mock_ensure_storage: unittest.mock.Mock,
    ) -> None:
        folder = self.tmpdir / "custom" / "DRP000009"
        folder.mkdir(parents=True)
        marker = folder / "data.zip"
        marker.write_bytes(b"zip")

        with patch("storage.Storage") as mock_storage, patch(
            "interactive_collector.api_projects.get_base_output_dir"
        ) as mock_base:
            mock_storage.get.return_value = {"folder_path": str(folder)}
            path = ensure_output_folder(9, recreate=False)
            mock_base.assert_not_called()
        self.assertEqual(path, str(folder))
        self.assertTrue(marker.exists())

    @patch("interactive_collector.api_projects._ensure_storage")
    def test_recreate_true_wipes_storage_folder_path(
        self,
        _mock_ensure_storage: unittest.mock.Mock,
    ) -> None:
        folder = self.tmpdir / "custom" / "DRP000011"
        folder.mkdir(parents=True)
        marker = folder / "data.zip"
        marker.write_bytes(b"zip")

        with patch("storage.Storage") as mock_storage, patch(
            "interactive_collector.api_projects.get_base_output_dir"
        ) as mock_base:
            mock_storage.get.return_value = {"folder_path": str(folder)}
            path = ensure_output_folder(11, recreate=True)
            mock_base.assert_not_called()
        self.assertEqual(path, str(folder))
        self.assertTrue(folder.is_dir())
        self.assertFalse(marker.exists())


class TestInteractivePrereq(unittest.TestCase):
    """Tests for interactive_collector eligibility prereq selection."""

    def setUp(self) -> None:
        """Initialize Args and Logger for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "interactive_collector"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore argv and default prereq flag."""
        Args._config["interactive_external_archive"] = False
        sys.argv = self._original_argv

    def test_get_interactive_prereq_defaults_to_sourced(self) -> None:
        """Default prereq is sourced."""
        Args._config["interactive_external_archive"] = False
        self.assertEqual(get_interactive_prereq(), STATUS_SOURCED)

    def test_get_interactive_prereq_external_archive_flag(self) -> None:
        """--external-archive selects collected - external archive."""
        Args._config["interactive_external_archive"] = True
        self.assertEqual(get_interactive_prereq(), STATUS_EXTERNAL_ARCHIVE)

    @patch("interactive_collector.api_projects._ensure_storage")
    @patch("storage.Storage")
    def test_get_first_eligible_uses_external_archive_prereq(
        self,
        mock_storage: MagicMock,
        _mock_ensure: MagicMock,
    ) -> None:
        """First eligible lists projects with external-archive status when flag set."""
        Args._config["interactive_external_archive"] = True
        project = {
            "DRPID": 223,
            "source_url": "https://example.com/x",
            "status": STATUS_EXTERNAL_ARCHIVE,
        }
        mock_storage.list_eligible_projects.return_value = [project]

        result = get_first_eligible()

        self.assertEqual(result, project)
        mock_storage.list_eligible_projects.assert_called_once_with(
            STATUS_EXTERNAL_ARCHIVE,
            1,
            None,
            None,
        )

    @patch("interactive_collector.api_projects._ensure_storage")
    @patch("storage.Storage")
    def test_get_next_eligible_after_uses_external_archive_prereq(
        self,
        mock_storage: MagicMock,
        _mock_ensure: MagicMock,
    ) -> None:
        """Next eligible uses external-archive status when flag set."""
        Args._config["interactive_external_archive"] = True
        projects = [
            {"DRPID": 223, "source_url": "https://a.example"},
            {"DRPID": 251, "source_url": "https://b.example"},
        ]
        mock_storage.list_eligible_projects.return_value = projects

        result = get_next_eligible_after(223)

        self.assertEqual(result["DRPID"], 251)
        mock_storage.list_eligible_projects.assert_called_once_with(
            STATUS_EXTERNAL_ARCHIVE,
            200,
            None,
            None,
        )


if __name__ == "__main__":
    unittest.main()
