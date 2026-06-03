"""Tests for scripts.cleanup_updated_inventory_folders."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.cleanup_updated_inventory_folders import (
    evaluate_folder,
    fetch_candidates,
    plan_cleanups,
    row_has_no_errors,
)


class TestCleanupUpdatedInventoryFolders(unittest.TestCase):
    def test_row_has_no_errors(self) -> None:
        self.assertTrue(row_has_no_errors(None))
        self.assertTrue(row_has_no_errors(""))
        self.assertTrue(row_has_no_errors("   "))
        self.assertFalse(row_has_no_errors("upload failed"))

    def test_fetch_candidates_filters_status_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                CREATE TABLE projects (
                    DRPID INTEGER PRIMARY KEY,
                    status TEXT,
                    errors TEXT,
                    folder_path TEXT
                )
                """
            )
            conn.executemany(
                "INSERT INTO projects (DRPID, status, errors, folder_path) VALUES (?, ?, ?, ?)",
                [
                    (1, "updated_inventory", None, r"C:\data\DRP000001"),
                    (2, "updated_inventory", "oops", r"C:\data\DRP000002"),
                    (3, "uploaded", None, r"C:\data\DRP000003"),
                ],
            )
            conn.commit()
            rows = fetch_candidates(conn)
            conn.close()
            self.assertEqual([r["DRPID"] for r in rows], [1])

    def test_plan_cleanups_skips_missing_folder(self) -> None:
        planned = plan_cleanups(
            [
                {
                    "DRPID": 9,
                    "folder_path": r"C:\no\such\DRP000009",
                    "errors": None,
                }
            ],
            compute_size=False,
        )
        self.assertEqual(planned[0].note, "skip — path does not exist")

    def test_evaluate_folder_ready_to_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "DRP000099"
            folder.mkdir()
            (folder / "a.txt").write_text("x", encoding="utf-8")
            row = evaluate_folder(99, str(folder), compute_size=True)
            self.assertEqual(row.note, "delete")
            self.assertEqual(row.size_bytes, 1)


if __name__ == "__main__":
    unittest.main()
