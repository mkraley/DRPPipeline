"""Tests for interactive_collector.api_projects."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interactive_collector.api_projects import ensure_output_folder
from interactive_collector.collector_state import get_result_by_drpid


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


if __name__ == "__main__":
    unittest.main()
