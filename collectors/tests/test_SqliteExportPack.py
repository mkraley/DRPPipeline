"""Tests for packing SQLite and GeoPackage exports."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from collectors.SqliteExportPack import pack_sqlite_export


class TestSqliteExportPack(unittest.TestCase):
    """GeoPackage and SQLite downloads become named zip archives."""

    def test_geopackage_is_stored_as_layer_gpkg_zip(self) -> None:
        """A GeoPackage becomes ``{layer}_gpkg.zip`` and the raw file is removed."""
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "Final_geoPackage.gpkg"
            raw.write_bytes(b"SQLite format 3\x00gpkg")
            packed = pack_sqlite_export(raw)
            self.assertEqual(packed.name, "Final_gpkg.zip")
            self.assertFalse(raw.exists())
            with zipfile.ZipFile(packed) as archive:
                self.assertEqual(archive.namelist(), ["Final_geoPackage.gpkg"])
                self.assertEqual(archive.read("Final_geoPackage.gpkg"), b"SQLite format 3\x00gpkg")
                info = archive.getinfo("Final_geoPackage.gpkg")
            self.assertEqual(info.compress_type, zipfile.ZIP_STORED)

    def test_sqlite_is_stored_as_layer_sqlite_zip(self) -> None:
        """A SQLite geodatabase becomes ``{layer}_sqlite.zip``."""
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "Buyer_Seller_sqlite.sqlite"
            raw.write_bytes(b"database")
            packed = pack_sqlite_export(raw)
            self.assertEqual(packed.name, "Buyer_Seller_sqlite.zip")
            self.assertFalse(raw.exists())

    def test_other_files_are_left_alone(self) -> None:
        """A CSV is not packed."""
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "Final_csv.csv"
            raw.write_bytes(b"a,b")
            self.assertEqual(pack_sqlite_export(raw), raw)
            self.assertTrue(raw.is_file())

    def test_existing_archive_replaces_the_raw_file(self) -> None:
        """A second raw copy is removed when the zip is already present."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            archive = folder / "Final_gpkg.zip"
            archive.write_bytes(b"already")
            raw = folder / "Final_geoPackage.gpkg"
            raw.write_bytes(b"again")
            packed = pack_sqlite_export(raw)
            self.assertEqual(packed, archive)
            self.assertEqual(archive.read_bytes(), b"already")
            self.assertFalse(raw.exists())


if __name__ == "__main__":
    unittest.main()
