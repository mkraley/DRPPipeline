"""Tests for zip archive extension scanning."""

from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from utils.zip_extension_scan import (
    ZipExtensionScanBudget,
    scan_zip_extensions_in_folder,
)


class TestZipExtensionScan(unittest.TestCase):
    """Tests for scan_zip_extensions_in_folder."""

    def setUp(self) -> None:
        """Create a temp folder for archive fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        """Remove temp folder."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_scans_member_extensions_from_zip(self) -> None:
        """Top-level zip members contribute extensions."""
        zip_path = self.temp_dir / "dataset.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("roads/roads.shp", b"shape")
            archive.writestr("roads/roads.dbf", b"data")
            archive.writestr("readme.txt", b"notes")

        result = scan_zip_extensions_in_folder(self.temp_dir)
        self.assertEqual(result.extensions, {"dbf", "shp", "txt"})
        self.assertEqual(result.archives_scanned, 1)

    def test_recurses_into_nested_zip(self) -> None:
        """Nested zip members are scanned within the depth budget."""
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as nested:
            nested.writestr("metrics.csv", b"1,2,3")

        zip_path = self.temp_dir / "outer.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("inner.zip", inner.getvalue())

        result = scan_zip_extensions_in_folder(self.temp_dir)
        self.assertIn("csv", result.extensions)
        self.assertGreaterEqual(result.archives_scanned, 2)

    def test_respects_archive_count_budget(self) -> None:
        """Archive count budget stops scanning additional zips."""
        for index in range(3):
            zip_path = self.temp_dir / f"part{index}.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(f"file{index}.csv", b"x")

        budget = ZipExtensionScanBudget(max_archives=2)
        result = scan_zip_extensions_in_folder(self.temp_dir, budget)
        self.assertEqual(result.archives_scanned, 2)
        self.assertTrue(result.budget_exhausted)

    def test_respects_depth_budget(self) -> None:
        """Depth budget prevents scanning deeply nested archives."""
        level3 = io.BytesIO()
        with zipfile.ZipFile(level3, "w") as archive:
            archive.writestr("deep.shp", b"x")

        level2 = io.BytesIO()
        with zipfile.ZipFile(level2, "w") as archive:
            archive.writestr("level3.zip", level3.getvalue())

        level1 = io.BytesIO()
        with zipfile.ZipFile(level1, "w") as archive:
            archive.writestr("level2.zip", level2.getvalue())

        zip_path = self.temp_dir / "level1.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("level1.zip", level1.getvalue())

        budget = ZipExtensionScanBudget(max_depth=2)
        result = scan_zip_extensions_in_folder(self.temp_dir, budget)
        self.assertNotIn("shp", result.extensions)

    def test_scans_tar_member_inside_zip(self) -> None:
        """Tar archives inside zips contribute member extensions."""
        tar_bytes = io.BytesIO()
        with tarfile.open(fileobj=tar_bytes, mode="w") as archive:
            data = b"tabular"
            info = tarfile.TarInfo(name="table.csv")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

        zip_path = self.temp_dir / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("bundle.tar", tar_bytes.getvalue())

        result = scan_zip_extensions_in_folder(self.temp_dir)
        self.assertIn("csv", result.extensions)


if __name__ == "__main__":
    unittest.main()
