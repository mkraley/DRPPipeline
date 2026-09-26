"""Tests for NPS download planning helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from collectors.NpsDownloadPlan import (
    PRODUCT_FOLDER_MAX_LENGTH,
    NpsPlannedFile,
    fit_planned_files,
    planned_files_for_profile,
    product_folder_name,
    sidecar_filename,
    unique_product_folder_name,
)


class TestNpsDownloadPlan(unittest.TestCase):
    """Tests for product folders and planned Digital Files."""

    def test_product_folder_name_uses_title_only(self) -> None:
        """Folder names use the product title and omit the IRMA id."""
        name = product_folder_name("Mammal inventory: Blue Ridge?")
        self.assertNotIn("663485", name)
        self.assertFalse(name[:1].isdigit())
        self.assertNotIn("?", name)
        self.assertIn("Mammal", name)

    def test_product_folder_name_max_length(self) -> None:
        """Product folder names are capped for Windows path headroom."""
        title = "Mercury and other trace element wet deposition in Alaska " * 3
        name = product_folder_name(title)
        self.assertLessEqual(len(name), PRODUCT_FOLDER_MAX_LENGTH)

    def test_unique_product_folder_name_disambiguates(self) -> None:
        """Duplicate titles get a numeric suffix instead of an IRMA id."""
        used: set[str] = set()
        first = unique_product_folder_name("Same Title", used)
        second = unique_product_folder_name("Same Title", used)
        self.assertNotEqual(first, second)
        self.assertTrue(second.startswith(first))

    def test_unique_product_folder_name_notes_original(self) -> None:
        """Shortened folders record the original title for collection notes."""
        used: set[str] = set()
        notes: list[str] = []
        title = (
            "Mercury and other trace element wet deposition in Alaska spatial "
            "patterns, controlling factors, and source regions"
        )
        name = unique_product_folder_name(title, used, notes)
        self.assertLessEqual(len(name), PRODUCT_FOLDER_MAX_LENGTH)
        self.assertEqual(len(notes), 1)
        self.assertIn(title, notes[0])
        self.assertIn(name, notes[0])
        self.assertIn("Original product folder:", notes[0])

    def test_sidecar_filename(self) -> None:
        """Sidecars sit next to the CSV they describe."""
        self.assertEqual(sidecar_filename("HUC.csv"), "HUC_data_table_info.csv")

    def test_planned_files_skip_external_links_and_merge_holdings(self) -> None:
        """Only Digital Files are planned; holdings supply size and table count."""
        profile = {
            "referenceId": 2308545,
            "visibility": "Public",
            "filesAndLinks": [
                {
                    "fileId": 716591,
                    "resourceType": "Digital File",
                    "url": "https://irma.nps.gov/DataStore/DownloadFile/716591",
                    "fileName": "HUC.csv",
                },
                {
                    "resourceType": "External Link",
                    "url": "https://example.com",
                    "fileName": "website",
                },
            ],
        }
        holdings = [
            {
                "Id": 716591,
                "Url": "https://irma.nps.gov/DataStore/DownloadFile/716591",
                "FileDescription": "HUC.csv",
                "FileSize": 100,
                "DataTableCount": 2,
            }
        ]
        planned = planned_files_for_profile(profile, "2308545_pkg", holdings)
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0].filename, "HUC.csv")
        self.assertEqual(planned[0].size_bytes, 100)
        self.assertEqual(planned[0].data_table_count, 2)
        self.assertEqual(planned[0].relative_dir, "2308545_pkg")

    def test_fit_planned_files_shortens_for_max_path(self) -> None:
        """Long folder+file destinations are truncated to fit Windows MAX_PATH."""
        with tempfile.TemporaryDirectory() as tmp:
            folder_path = Path(tmp) / ("NPS" + "0" * 20)
            folder_path.mkdir()
            long_dir = (
                "Mercury_and_other_trace_element_wet_deposition_in_Alaska_"
                "spatial_patterns_controlling_factors_and_source_regions"
            )[:80]
            long_file = (
                "Obrist_et_al._2016._Mercury_and_other_trace_elements_wet_deposition_"
                "in_AK_-_Spatial_patterns_controlling_factors_and_sources."
                "NPS_Draft_Report_113016.pdf"
            )
            entry = NpsPlannedFile(
                url="https://example.com/f",
                filename=long_file,
                relative_dir=long_dir,
                original_filename=long_file,
            )
            fitted, notes, _renames = fit_planned_files(
                folder_path, [entry], max_path_length=259
            )
            dest = folder_path / fitted[0].relative_dir / fitted[0].filename
            self.assertLessEqual(len(str(dest)), 259)
            self.assertTrue(fitted[0].filename.lower().endswith(".pdf"))
            self.assertTrue(any(note.startswith("Original file:") for note in notes))

    def test_fit_planned_files_leaves_room_for_win32_nul(self) -> None:
        """Paths must be at most 259 chars (Win32 MAX_PATH includes a NUL)."""
        with tempfile.TemporaryDirectory() as tmp:
            folder_path = Path(tmp) / "NPS000009"
            folder_path.mkdir()
            long_dir = ("Mercury_and_other_trace_element_wet_deposition_" * 3)[:80]
            long_file = (
                "Obrist_et_al._2016._Mercury_and_other_trace_elements_wet_deposition_"
                "in_AK_-_Spatial_patterns_controlling_factors_and_sources."
                "NPS_Draft_Report_113016.pdf"
            )
            entry = NpsPlannedFile(
                url="https://example.com/f",
                filename=long_file,
                relative_dir=long_dir,
                original_filename=long_file,
            )
            # Simulate the real NPS000009 base length so the fit is tight.
            fake_base = Path(r"C:\DataRescue\NPSData\NPS000009")
            fitted, _notes, _renames = fit_planned_files(fake_base, [entry])
            dest = fake_base / fitted[0].relative_dir / fitted[0].filename
            self.assertLessEqual(len(str(dest)), 259)
            self.assertTrue(fitted[0].filename.lower().endswith(".pdf"))


if __name__ == "__main__":
    unittest.main()
