"""Tests for scripts.normalize_project_titles."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.normalize_project_titles import normalize_titles_in_db


class TestNormalizeProjectTitles(unittest.TestCase):
    """Tests for database title normalization script."""

    def test_normalize_titles_in_db_updates_matching_rows(self) -> None:
        """Rows with catalog suffixes are rewritten; others are unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE projects (drpid INTEGER PRIMARY KEY, title TEXT)"
            )
            conn.executemany(
                "INSERT INTO projects (drpid, title) VALUES (?, ?)",
                [
                    (1, "Clean Title"),
                    (2, "HFMD | Agency for Healthcare Research and Quality"),
                    (3, "Quality Measures | Medicaid"),
                ],
            )
            conn.commit()
            conn.close()

            updated = normalize_titles_in_db(db_path)
            self.assertEqual(updated, 2)

            conn = sqlite3.connect(db_path)
            rows = dict(conn.execute("SELECT drpid, title FROM projects").fetchall())
            conn.close()
            self.assertEqual(rows[1], "Clean Title")
            self.assertEqual(rows[2], "HFMD")
            self.assertEqual(rows[3], "Quality Measures")

    def test_normalize_titles_in_db_dry_run_makes_no_changes(self) -> None:
        """Dry run reports but does not write."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE projects (drpid INTEGER PRIMARY KEY, title TEXT)"
            )
            conn.execute(
                "INSERT INTO projects (drpid, title) VALUES (1, 'X | Medicaid')"
            )
            conn.commit()
            conn.close()

            updated = normalize_titles_in_db(db_path, dry_run=True)
            self.assertEqual(updated, 1)

            conn = sqlite3.connect(db_path)
            title = conn.execute("SELECT title FROM projects WHERE drpid = 1").fetchone()[0]
            conn.close()
            self.assertEqual(title, "X | Medicaid")
