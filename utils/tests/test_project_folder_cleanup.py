"""Tests for utils.project_folder_cleanup."""

import tempfile
import unittest
from pathlib import Path

from utils.project_folder_cleanup import (
    evaluate_project_folder,
    row_has_no_errors,
    try_delete_project_folder,
)


class TestProjectFolderCleanup(unittest.TestCase):
    def test_row_has_no_errors(self) -> None:
        self.assertTrue(row_has_no_errors(None))
        self.assertTrue(row_has_no_errors(""))
        self.assertFalse(row_has_no_errors("upload failed"))

    def test_try_delete_project_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "DRP000001"
            folder.mkdir()
            marker = folder / "data.txt"
            marker.write_text("x", encoding="utf-8")

            result = try_delete_project_folder(1, str(folder))
            self.assertTrue(result.deleted)
            self.assertFalse(folder.exists())

    def test_try_delete_missing_folder(self) -> None:
        result = try_delete_project_folder(1, r"C:\no\such\DRP000001")
        self.assertFalse(result.deleted)
        self.assertIn("does not exist", result.message)

    def test_evaluate_project_folder_with_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "DRP000099"
            folder.mkdir()
            (folder / "a.txt").write_text("x", encoding="utf-8")
            result = evaluate_project_folder(99, str(folder), compute_size=True)
            self.assertTrue(result.deleted)


if __name__ == "__main__":
    unittest.main()
