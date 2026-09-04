"""Tests for scripts.replace_title_colons."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.replace_title_colons import replace_title_colons_in_db


class TestReplaceTitleColons(unittest.TestCase):
    """Tests for one-time colon replacement in project titles."""

    def setUp(self) -> None:
        """Create a temporary projects table with colon titles."""
        self._temp_dir = Path(tempfile.mkdtemp())
        self._db_path = self._temp_dir / "test.db"
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute(
            "CREATE TABLE projects (drpid INTEGER PRIMARY KEY, title TEXT)"
        )
        self._conn.executemany(
            "INSERT INTO projects (drpid, title) VALUES (?, ?)",
            [
                (1, "Atlas Databases: 2003"),
                (2, "Plain Title"),
                (3, "City/Airport: Q4"),
            ],
        )
        self._conn.commit()

    def tearDown(self) -> None:
        """Close and remove the temporary database."""
        self._conn.close()
        self._db_path.unlink(missing_ok=True)
        self._temp_dir.rmdir()

    def test_dry_run_does_not_write(self) -> None:
        """Dry-run reports changes without updating rows."""
        count = replace_title_colons_in_db(self._db_path, dry_run=True)
        self.assertEqual(count, 2)
        title = self._conn.execute(
            "SELECT title FROM projects WHERE drpid = 1"
        ).fetchone()[0]
        self.assertEqual(title, "Atlas Databases: 2003")

    def test_updates_colon_titles(self) -> None:
        """Colon titles are rewritten with em dashes."""
        count = replace_title_colons_in_db(self._db_path, dry_run=False)
        self.assertEqual(count, 2)
        rows = {
            int(r[0]): r[1]
            for r in self._conn.execute("SELECT drpid, title FROM projects").fetchall()
        }
        self.assertEqual(rows[1], "Atlas Databases — 2003")
        self.assertEqual(rows[2], "Plain Title")
        self.assertEqual(rows[3], "City/Airport — Q4")


if __name__ == "__main__":
    unittest.main()
