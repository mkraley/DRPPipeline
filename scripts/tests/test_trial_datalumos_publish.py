"""Tests for the one-project DataLumos HTTP publish trial."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.trial_datalumos_deposit import require_trial_drpid
from scripts.trial_datalumos_publish import (
    main,
    project_can_publish,
    record_published,
)
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger


class TestTrialDataLumosPublish(unittest.TestCase):
    """Guards for the live publish trial."""

    def setUp(self) -> None:
        """Temp Storage so a confirmed view can be written."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "publish"]
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="ERROR", log_file=False)
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize(
            "StorageSQLLite", db_path=self.temp_dir / "test.db"
        )

    def tearDown(self) -> None:
        """Close the temp database."""
        import shutil

        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        Args._initialized = False
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_drpid_at_2500_is_refused(self) -> None:
        """Current batches stay on ids at or below 2500."""
        with self.assertRaises(ValueError):
            require_trial_drpid(2500)

    def test_missing_datalumos_id_is_refused(self) -> None:
        """A row that was never uploaded cannot be published."""
        message = project_can_publish({"status": "uploaded"}, 2600)
        self.assertIn("datalumos_id", message)

    def test_low_drpid_exits_before_storage(self) -> None:
        """DRPID 2500 does not open config or the database."""
        with patch("scripts.trial_datalumos_publish._load_project") as load_project:
            code = main(["--drpid", "2500"])
        self.assertEqual(code, 1)
        load_project.assert_not_called()

    def test_unpublished_view_does_not_update_storage(self) -> None:
        """A view URL that is not public leaves the project uploaded."""
        drpid = Storage.create_record("https://example.com/data")
        Storage.update_record(drpid, {"status": "uploaded", "datalumos_id": "9"})
        updated = record_published(
            drpid,
            "https://www.datalumos.org/datalumos/project/9/version/V1/view",
            False,
        )
        project = Storage.get(drpid)
        assert project is not None
        self.assertFalse(updated)
        self.assertEqual(project["status"], "uploaded")
        self.assertIsNone(project.get("published_url"))

    def test_public_view_marks_the_project_published(self) -> None:
        """A confirmed view URL is the only path that writes published status."""
        drpid = Storage.create_record("https://example.com/data")
        Storage.update_record(drpid, {"status": "uploaded"})
        view_url = "https://www.datalumos.org/datalumos/project/9/version/V1/view"
        self.assertTrue(record_published(drpid, view_url, True))
        project = Storage.get(drpid)
        assert project is not None
        self.assertEqual(project["status"], "published")
        self.assertEqual(project["published_url"], view_url)


if __name__ == "__main__":
    unittest.main()
