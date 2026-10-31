"""Unit tests for the browser-form upload path."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from upload.FormProjectUpload import FormProjectUpload
from upload.UploadIssueReporter import UploadIssueReporter


class TestFormProjectUpload(unittest.TestCase):
    """The form path stores the new workspace id before filling metadata."""

    def setUp(self) -> None:
        """Initialize Args so the form filler timeout can be read."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "upload", "--ui-upload"]
        Args._initialized = False
        Args._config = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore argv and Args."""
        sys.argv = self._original_argv
        Args._initialized = False
        Args._config = {}

    @patch("upload.DataLumosAuthenticator.wait_for_human_verification")
    @patch("upload.DataLumosFormFiller.DataLumosFormFiller")
    @patch("upload.FormProjectUpload.Storage")
    def test_saves_workspace_id_before_metadata(
        self,
        storage: MagicMock,
        filler_cls: MagicMock,
        _verification: MagicMock,
    ) -> None:
        """datalumos_id is written after the title save and before the other fields."""
        order: list[str] = []
        page = MagicMock()
        page.url = "https://www.datalumos.org/datalumos/workspace?goToPath=/datalumos/77#"
        filler = filler_cls.return_value
        storage.update_record.side_effect = lambda *_args, **_kwargs: order.append("save")
        filler.fill_summary.side_effect = lambda *_args, **_kwargs: order.append("summary")
        workspace_id = FormProjectUpload(
            page, "https://www.datalumos.org/datalumos/workspace"
        ).create_and_fill(
            {"title": "River gauges", "summary": "A set."},
            2501,
            UploadIssueReporter(2501),
        )
        self.assertEqual(workspace_id, "77")
        self.assertEqual(order, ["save", "summary"])
        storage.update_record.assert_called_once_with(2501, {"datalumos_id": "77"})


if __name__ == "__main__":
    unittest.main()
