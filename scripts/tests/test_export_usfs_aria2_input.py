"""Tests for scripts.export_usfs_aria2_input skip-note fallback."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collectors.UsfsAria2Export import parse_aria2c_lines_from_cmd_file


def _make_conn(folder: Path, status_notes: str, source_url: str = "https://x/1") -> sqlite3.Connection:
    """Create an in-memory projects table with one DRP 157-like row."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE projects (DRPID INTEGER, source_url TEXT, "
        "folder_path TEXT, status_notes TEXT)"
    )
    conn.execute(
        "INSERT INTO projects VALUES (?, ?, ?, ?)",
        (157, source_url, str(folder), status_notes),
    )
    return conn


class TestExportDrpidSkipNoteFallback(unittest.TestCase):
    """export_drpid falls back to status_notes when the catalog has no files."""

    def test_falls_back_to_status_notes_links(self) -> None:
        from scripts.export_usfs_aria2_input import export_drpid

        notes = (
            "Skipped download (>1GB): A01L4_1.zip (2.9 GB) - "
            "download manually: https://ndownloader.figshare.com/files/43634028\n"
            "Skipped download (>1GB): X01wp_1.zip (3.1 GB) - "
            "download manually: https://ndownloader.figshare.com/files/43634061"
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "DRP000157"
            folder.mkdir()
            out_dir = Path(tmp) / "aria2_inputs"
            conn = _make_conn(folder, notes)
            # Simulate a non-USFS page: no catalog publication files.
            with patch(
                "scripts.export_usfs_aria2_input.catalog_publication_files",
                return_value=[],
            ):
                count = export_drpid(
                    conn,
                    157,
                    out_dir,
                    Path(tmp),
                    "UA",
                    min_bytes=1 * 1024**3,
                    missing_only=True,
                    combined_entries=[],
                )
            conn.close()

            self.assertEqual(count, 2)
            cmd_path = out_dir / "DRP000157.cmd"
            self.assertTrue(cmd_path.is_file())
            lines = parse_aria2c_lines_from_cmd_file(cmd_path)
            joined = "\n".join(lines)
            self.assertIn("43634028", joined)
            self.assertIn("A01L4_1.zip", joined)

    def test_skips_files_already_on_disk(self) -> None:
        from scripts.export_usfs_aria2_input import export_drpid

        notes = (
            "Skipped download (>1GB): keep.zip (2.9 GB) - "
            "download manually: https://ndownloader.figshare.com/files/1"
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "DRP000157"
            folder.mkdir()
            (folder / "keep.zip").write_bytes(b"x")
            out_dir = Path(tmp) / "aria2_inputs"
            conn = _make_conn(folder, notes)
            with patch(
                "scripts.export_usfs_aria2_input.catalog_publication_files",
                return_value=[],
            ):
                count = export_drpid(
                    conn,
                    157,
                    out_dir,
                    Path(tmp),
                    "UA",
                    min_bytes=1 * 1024**3,
                    missing_only=True,
                    combined_entries=[],
                )
            conn.close()

            self.assertEqual(count, 0)
            self.assertFalse((out_dir / "DRP000157.cmd").is_file())

    def test_prefers_catalog_files_when_present(self) -> None:
        from scripts.export_usfs_aria2_input import export_drpid

        notes = (
            "Skipped download (>1GB): fromnotes.zip (2.9 GB) - "
            "download manually: https://ndownloader.figshare.com/files/1"
        )
        catalog = [("catalog.zip", "https://fs.usda.gov/catalog.zip", 3 * 1024**3)]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "DRP000157"
            folder.mkdir()
            out_dir = Path(tmp) / "aria2_inputs"
            conn = _make_conn(folder, notes)
            with patch(
                "scripts.export_usfs_aria2_input.catalog_publication_files",
                return_value=catalog,
            ):
                count = export_drpid(
                    conn,
                    157,
                    out_dir,
                    Path(tmp),
                    "UA",
                    min_bytes=1 * 1024**3,
                    missing_only=True,
                    combined_entries=[],
                )
            conn.close()

            self.assertEqual(count, 1)
            lines = parse_aria2c_lines_from_cmd_file(out_dir / "DRP000157.cmd")
            joined = "\n".join(lines)
            self.assertIn("catalog.zip", joined)
            self.assertNotIn("fromnotes.zip", joined)


if __name__ == "__main__":
    unittest.main()
