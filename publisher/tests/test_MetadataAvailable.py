"""Tests for Baserow Metadata available file checks."""

import tempfile
import unittest
from pathlib import Path

from publisher.MetadataAvailable import folder_has_metadata_files, metadata_available_cell


class TestMetadataAvailable(unittest.TestCase):
    """check_files scans project file names for metadata or table_info."""

    def test_bool_settings_skip_the_folder(self) -> None:
        self.assertEqual(metadata_available_cell(True, None), "yes")
        self.assertEqual(metadata_available_cell(False, None), "no")

    def test_check_files_yes_when_name_contains_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "FGDC_metadata.xml").write_text("<x/>", encoding="utf-8")
            self.assertEqual(metadata_available_cell("check_files", str(root)), "yes")

    def test_check_files_ignores_landing_metadata_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project_metadata.json").write_text("{}", encoding="utf-8")
            product = root / "pkg"
            product.mkdir()
            (product / "product_metadata.json").write_text("{}", encoding="utf-8")
            self.assertEqual(metadata_available_cell("check_files", str(root)), "no")

    def test_check_files_yes_for_nested_table_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "product"
            nested.mkdir()
            (nested / "HUC_data_table_info.csv").write_text("a\n", encoding="utf-8-sig")
            self.assertTrue(folder_has_metadata_files(str(root)))

    def test_check_files_no_when_names_do_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readings.csv").write_text("a\n", encoding="utf-8-sig")
            self.assertEqual(metadata_available_cell("CHECK_FILES", str(root)), "no")

    def test_check_files_no_when_folder_missing(self) -> None:
        self.assertEqual(metadata_available_cell("check_files", ""), "no")


if __name__ == "__main__":
    unittest.main()
