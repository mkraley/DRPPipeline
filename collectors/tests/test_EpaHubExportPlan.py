"""Tests for Clip and Ship export names."""

from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from collectors.EpaHubExportPlan import (
    corrected_zip_export,
    file_specs,
    name_with_export_extension,
)


class TestEpaHubExportPlan(unittest.TestCase):
    """Export filenames use the extension of the generated file."""

    def test_kml_and_feature_collection_are_not_zip(self) -> None:
        """KML is .kml and a feature collection is .json."""
        feature = {"id": "ab" * 16, "properties": {}}
        service = {
            "layers": [{"id": 16, "name": "cattle"}],
            "supportedExportFormats": "kml,featureCollection,shapefile",
        }
        names = [name for name, _url in file_specs(feature, service)]
        self.assertIn("cattle_kml.kml", names)
        self.assertIn("cattle_featureCollection.json", names)
        self.assertIn("cattle_shapefile.zip", names)

    def test_sqlite_export_is_requested(self) -> None:
        """SQLite is requested so it can be stored as a zip."""
        feature = {"id": "ab" * 16, "properties": {}}
        service = {
            "layers": [{"id": 0, "name": "Sites"}],
            "supportedExportFormats": "csv,sqlite,shapefile",
        }
        names = [name for name, _url in file_specs(feature, service)]
        self.assertEqual(names, ["Sites_csv.csv", "Sites_sqlite.sqlite", "Sites_shapefile.zip"])

    def test_tables_are_requested_with_layers(self) -> None:
        """A standalone table is downloaded with the same formats as a layer."""
        feature = {"id": "ab" * 16, "properties": {}}
        service = {
            "layers": [{"id": 0, "name": "Final"}],
            "tables": [{"id": 2, "name": "Buyer_Seller"}],
            "supportedExportFormats": "csv",
        }
        names = [name for name, _url in file_specs(feature, service)]
        self.assertEqual(names, ["Final_csv.csv", "Buyer_Seller_csv.csv"])
        urls = [url for _name, url in file_specs(feature, service)]
        self.assertIn("layers=2", urls[1])

    def test_duplicate_layer_and_table_names_stay_distinct(self) -> None:
        """A table that repeats a layer name gets its id in the filename."""
        feature = {"id": "ab" * 16, "properties": {}}
        service = {
            "layers": [{"id": 0, "name": "Final"}],
            "tables": [{"id": 2, "name": "Final"}],
            "supportedExportFormats": "csv",
        }
        names = [name for name, _url in file_specs(feature, service)]
        self.assertEqual(names, ["Final_csv.csv", "Final_2_csv.csv"])

    def test_result_url_extension_replaces_the_planned_suffix(self) -> None:
        """A generated .kmz is not saved under the planned .kml name."""
        url = "https://services.arcgis.com/cache/All_cattle.kml?token=1"
        self.assertEqual(
            name_with_export_extension("cattle_kml.zip", url),
            "cattle_kml.kml",
        )
        self.assertEqual(
            name_with_export_extension("Sites_csv.csv", "https://files.example/layer.zip"),
            "Sites_csv.csv",
        )

    def test_kml_bytes_saved_as_zip_are_renamed(self) -> None:
        """A previous .zip whose bytes are KML becomes .kml."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cattle_kml.zip"
            path.write_bytes(b'<?xml version="1.0" ?><kml></kml>')
            renamed = corrected_zip_export(path)
        self.assertEqual(renamed.name, "cattle_kml.kml")
        self.assertFalse(path.exists())

    def test_json_bytes_saved_as_zip_are_renamed(self) -> None:
        """A previous .zip whose bytes are JSON becomes .json."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Sites_featureCollection.zip"
            path.write_bytes(b'{"layers": []}')
            renamed = corrected_zip_export(path)
        self.assertEqual(renamed.name, "Sites_featureCollection.json")

    def test_json_bytes_saved_as_txt_are_renamed(self) -> None:
        """Hub's feature-collection .txt is JSON and becomes .json."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Final_featureCollection.txt"
            path.write_bytes(b'{"layers": []}')
            renamed = corrected_zip_export(path)
        self.assertEqual(renamed.name, "Final_featureCollection.json")
        self.assertFalse(path.exists())

    def test_shapefile_zip_is_left_alone(self) -> None:
        """A zip that is not KML or JSON keeps its name."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cattle_shapefile.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("cattle.shp", b"shape")
            renamed = corrected_zip_export(path)
            self.assertEqual(renamed, path)
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
