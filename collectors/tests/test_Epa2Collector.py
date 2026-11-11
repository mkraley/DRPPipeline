"""Tests for Epa2Collector."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from collectors.Epa2Collector import LANDING_PDF_NAME, Epa2Collector
from collectors.PlannedFile import PlannedFile
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

_ITEM = "27cd1f0c43904460b27e9ab21449519b"
_DATASET_URL = f"https://edg-epa.hub.arcgis.com/datasets/{_ITEM}"
_PAGE_ID = "acc4a8f4aadf4e38941bf933bfd968fd"


def _feature(item_type: str = "Feature Service") -> dict:
    """Return a minimal Clip and Ship feature."""
    return {
        "id": _ITEM,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-112.0, 37.0], [-67.0, 37.0], [-67.0, 48.0], [-112.0, 37.0]]],
        },
        "properties": {
            "title": "NPL Boundaries",
            "type": item_type,
            "snippet": "Superfund boundaries",
            "source": "U.S. EPA Office of Land",
            "tags": ["Superfund", "Boundaries"],
            "url": "https://services.arcgis.com/org/arcgis/rest/services/NPL/FeatureServer",
        },
    }


class TestEpa2Collector(unittest.TestCase):
    """Tests for collecting one Clip and Ship item."""

    def setUp(self) -> None:
        """Point output and storage at a temporary folder."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "collect"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        Args._config["base_output_dir"] = str(self.temp_dir)
        Args._config["google_sheet_name"] = "EPA2"
        self.storage = Storage.initialize(
            "StorageSQLLite",
            db_path=self.temp_dir / "epa2.db",
        )

    def tearDown(self) -> None:
        """Restore argv and remove the temp folder."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_collect_prints_about_page_and_saves_metadata(self) -> None:
        """The landing PDF starts at the source page and follows full details."""
        pages = MagicMock()

        def _pdf(
            url: str,
            path: Path,
            spa_ready: bool = False,
            follow_full_details: bool = False,
        ) -> bool:
            self.assertTrue(spa_ready)
            self.assertTrue(follow_full_details)
            self.assertEqual(url, _DATASET_URL)
            path.write_bytes(b"%PDF-1.4")
            return True

        pages.url_to_pdf.side_effect = _pdf
        items = MagicMock()
        items.fetch_feature.return_value = _feature()
        exports = MagicMock()
        exports.download_all.return_value = (
            [],
            [PlannedFile("layer_csv.csv", "https://example.com/layer.csv", 8)],
        )
        exports.commit.return_value = "collected"
        collector = Epa2Collector(
            page_downloader=pages,
            item_client=items,
            exports=exports,
        )

        result = collector._collect(_DATASET_URL, 1, {})

        self.assertEqual(result["title"], "NPL Boundaries")
        self.assertEqual(result["agency"], "Environmental Protection Agency")
        self.assertEqual(result["office"], "Environmental Protection Agency")
        self.assertIn("Superfund", result["keywords"])
        self.assertIn("GIS", result["data_types"])
        self.assertTrue((Path(result["folder_path"]) / LANDING_PDF_NAME).is_file())
        exports.download_all.assert_called_once()

    def test_hub_page_prints_its_own_url(self) -> None:
        """A hub page is not rewritten to a dataset about URL."""
        pages = MagicMock()
        seen: list[str] = []

        def _pdf(
            url: str,
            path: Path,
            spa_ready: bool = False,
            follow_full_details: bool = False,
        ) -> bool:
            del spa_ready, follow_full_details
            seen.append(url)
            path.write_bytes(b"%PDF-1.4")
            return True

        pages.url_to_pdf.side_effect = _pdf
        items = MagicMock()
        feature = _feature("Hub Page")
        feature["id"] = _PAGE_ID
        items.fetch_feature.return_value = feature
        exports = MagicMock()
        exports.download_all.return_value = ([], [])
        exports.commit.return_value = "collected"
        source = f"https://edg-epa.hub.arcgis.com/pages/{_PAGE_ID}"
        Epa2Collector(
            page_downloader=pages,
            item_client=items,
            exports=exports,
        )._collect(source, 2, {})
        self.assertEqual(seen, [source])


if __name__ == "__main__":
    unittest.main()
