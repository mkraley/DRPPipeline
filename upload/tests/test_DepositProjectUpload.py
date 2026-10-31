"""Unit tests for production deposit-API project creation."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from upload.DepositProjectUpload import DepositProjectUpload


class TestDepositProjectUpload(unittest.TestCase):
    """Production create uses the real title and does not write a request log."""

    def test_create_posts_the_production_title_without_a_request_log(self) -> None:
        """The client is constructed with no log file and a title that is not marked TRIAL."""
        page = MagicMock()
        with patch("upload.DepositProjectUpload.DataLumosDepositClient") as client_cls:
            client = client_cls.return_value
            client.create_project.return_value = "/datalumos/259600"
            workspace_id = DepositProjectUpload(page).create(
                {"title": "River gauges", "summary": "A set."}
            )
        client_cls.assert_called_once_with(page, log_path=None)
        client.ensure_deposit_page.assert_called_once_with(None)
        title = client.create_project.call_args.args[0]
        self.assertNotIn("TRIAL", title)
        self.assertIn("River gauges", title)
        self.assertEqual(workspace_id, "259600")

    def test_fill_reuses_the_client(self) -> None:
        """Metadata is posted on the project path through the same client."""
        page = MagicMock()
        project = {"title": "River gauges", "summary": "A set."}
        with patch("upload.DepositProjectUpload.DataLumosDepositClient") as client_cls:
            client_cls.return_value.create_project.return_value = "/datalumos/11"
            with patch("upload.DepositProjectUpload.DepositMetadataWriter") as writer_cls:
                upload = DepositProjectUpload(page)
                upload.create(project)
                upload.fill("11", project)
        self.assertEqual(client_cls.call_count, 1)
        path, metadata = writer_cls.return_value.fill_metadata.call_args.args
        self.assertEqual(path, "/datalumos/11")
        self.assertNotIn("TRIAL", metadata.title)


if __name__ == "__main__":
    unittest.main()
