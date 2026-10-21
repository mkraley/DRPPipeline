"""Tests for the FERC metadata backfill."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.infer_ferc_metadata import field_updates, fill_ferc_metadata


class TestFieldUpdates(unittest.TestCase):
    """Tests for choosing which inferred values to store."""

    def test_empty_stored_fields_are_filled(self) -> None:
        """A blank stored field takes the inferred value."""
        updates = field_updates(
            {"keywords": "", "time_start": None},
            {"keywords": "hydrokinetic", "time_start": "2019"},
            overwrite=False,
        )
        self.assertEqual(updates["keywords"], "hydrokinetic")
        self.assertEqual(updates["time_start"], "2019")

    def test_stored_value_is_kept_unless_overwrite(self) -> None:
        """Overwrite is required before a stored value is replaced."""
        stored = {"geographic_coverage": "Alaska"}
        inferred = {"geographic_coverage": "United States"}
        self.assertEqual(field_updates(stored, inferred, overwrite=False), {})
        replaced = field_updates(stored, inferred, overwrite=True)
        self.assertEqual(replaced["geographic_coverage"], "United States")

    def test_overwrite_clears_a_keyword_inference_no_longer_supports(self) -> None:
        """Overwrite removes a stored keyword when the new inference has none."""
        updates = field_updates({"keywords": "company total revenue"}, {}, overwrite=True)
        self.assertEqual(updates["keywords"], "")


class TestFillFercMetadata(unittest.TestCase):
    """Tests for writing inferred fields onto collected projects."""

    def test_fill_uses_title_summary_and_dataset(self) -> None:
        """Collected projects gain dates, geography, and keywords from their files."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "FERC000007"
            folder.mkdir()
            (folder / "dataset.csv").write_text(
                "State,Issuance_Date\nAK,2019-05-23\nOR,2021-03-01\n",
                encoding="utf-8-sig",
            )
            (folder / "dictionary.csv").write_text(
                "attribute,description\nState,A state\n",
                encoding="utf-8-sig",
            )
            db_path = root / "ferc.db"
            self._insert_project(
                db_path,
                folder,
                title="Licensed Marine and Hydrokinetic Projects",
                summary="Hydrokinetic projects in the United States.",
            )

            updated = fill_ferc_metadata(db_path)

            row = self._read_project(db_path)
        self.assertEqual(updated, 1)
        self.assertEqual(row["geographic_coverage"], "United States")
        self.assertEqual(row["time_start"], "2019-05-23")
        self.assertEqual(row["time_end"], "2021-03-01")
        self.assertIn("hydrokinetic", row["keywords"])

    def test_dry_run_leaves_the_database_unchanged(self) -> None:
        """Dry run counts the project and does not write."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "FERC000007"
            folder.mkdir()
            (folder / "dataset.csv").write_text("Year\n2020\n", encoding="utf-8-sig")
            db_path = root / "ferc.db"
            self._insert_project(db_path, folder, title="Filings", summary="Filings since 2020.")

            updated = fill_ferc_metadata(db_path, dry_run=True)

            row = self._read_project(db_path)
        self.assertEqual(updated, 1)
        self.assertFalse(row["time_start"])

    def test_second_run_does_not_replace_a_stored_keyword(self) -> None:
        """A filled field stays put when overwrite is off."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "FERC000007"
            folder.mkdir()
            (folder / "dataset.csv").write_text(
                "Label,Year\nAlpha,2020\nBeta,2021\n",
                encoding="utf-8-sig",
            )
            db_path = root / "ferc.db"
            self._insert_project(
                db_path,
                folder,
                title="Filings",
                summary="Keywords: hydro; tidal.",
                keywords="kept",
            )

            fill_ferc_metadata(db_path)

            row = self._read_project(db_path)
        self.assertEqual(row["keywords"], "kept")
        self.assertEqual(row["time_start"], "2020")
        self.assertEqual(row["time_end"], "2021")

    def _insert_project(
        self,
        db_path: Path,
        folder: Path,
        *,
        title: str,
        summary: str,
        keywords: str = "",
    ) -> None:
        """Create a one-row projects table."""
        connection = sqlite3.connect(db_path)
        connection.execute(
            """
            CREATE TABLE projects (
                DRPID INTEGER PRIMARY KEY,
                title TEXT,
                summary TEXT,
                folder_path TEXT,
                keywords TEXT,
                time_start TEXT,
                time_end TEXT,
                data_types TEXT,
                geographic_coverage TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO projects (
                DRPID, title, summary, folder_path, keywords,
                time_start, time_end, data_types, geographic_coverage
            ) VALUES (7, ?, ?, ?, ?, '', '', '', '')
            """,
            (title, summary, str(folder), keywords),
        )
        connection.commit()
        connection.close()

    def _read_project(self, db_path: Path) -> sqlite3.Row:
        """Return the only project row."""
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM projects WHERE DRPID = 7").fetchone()
        connection.close()
        return row


if __name__ == "__main__":
    unittest.main()
