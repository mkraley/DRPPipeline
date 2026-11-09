"""Tests for the DataLumos publish HTTP client."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from publisher.DataLumosPublishClient import DataLumosPublishClient
from utils.Logger import Logger


class TestDataLumosPublishClient(unittest.TestCase):
    """Publish is one JSON POST after the terms reads."""

    def setUp(self) -> None:
        """Logger is required when a deposit call is recorded."""
        Logger.initialize(log_level="ERROR", log_file=False)

    def test_publish_posts_the_terms_body(self) -> None:
        """POST /publish carries the dialog answers and the review terms."""
        page = MagicMock()
        responses = [
            {"projectTitle": "Study"},
            {"depositAgreement": "text"},
            [{"groups": [{"attributes": [{"attribute": "licenseQuestion"}]}]}],
            [{"id": 15, "name": "Public Domain Mark"}],
            {"success": True},
        ]

        def fake_request(*_args: object, **kwargs: object) -> dict:
            payload = responses.pop(0)
            return {"status": 200, "body": json.dumps(payload), "elapsedMs": 1}

        with patch(
            "publisher.DataLumosPublishClient.prepare_deposit_token",
            return_value="jwt",
        ), patch(
            "publisher.DataLumosPublishClient.deposit_request",
            side_effect=fake_request,
        ) as request:
            DataLumosPublishClient(page).publish_project("9")

        post = request.call_args_list[-1]
        self.assertEqual(post.args[2], "POST")
        self.assertTrue(str(post.args[3]).endswith("/publish"))
        body = json.loads(str(post.kwargs["body"]))
        self.assertEqual(body["disclosureRisk"], "false")
        self.assertIs(body["agreed"], True)
        self.assertEqual(body["licenseId"], "15")
        self.assertNotIn("versionTitle", body)

    def test_login_redirect_is_not_a_public_view(self) -> None:
        """A navigation that lands on the login host is not confirmation."""
        from publisher.DataLumosPublishClient import _VIEW_ATTEMPTS

        page = MagicMock()
        checker = MagicMock()
        page.context.new_page.return_value = checker
        response = MagicMock()
        response.status = 200
        checker.goto.return_value = response
        checker.url = "https://login.icpsr.umich.edu/realms/icpsr"
        client = DataLumosPublishClient(page)
        with patch("publisher.DataLumosPublishClient.time.sleep"), patch(
            "publisher.DataLumosPublishClient.keep_browser_window_minimized"
        ) as minimize:
            public = client.view_is_public(
                "https://www.datalumos.org/datalumos/project/9/version/V1/view"
            )
        self.assertFalse(public)
        minimize.assert_called_once_with(checker)
        self.assertEqual(checker.goto.call_count, _VIEW_ATTEMPTS)
        checker.close.assert_called_once()

    def test_published_versions_marker_confirms_the_view(self) -> None:
        """A 200 project page is confirmation on the first load."""
        page = MagicMock()
        checker = MagicMock()
        page.context.new_page.return_value = checker
        response = MagicMock()
        response.status = 200
        checker.goto.return_value = response
        checker.url = "https://www.datalumos.org/datalumos/project/9/version/V1/view"
        checker.content.return_value = "<h2>Published Versions</h2>"
        client = DataLumosPublishClient(page)
        with patch(
            "publisher.DataLumosPublishClient.keep_browser_window_minimized"
        ) as minimize:
            self.assertTrue(
                client.view_is_public(
                    "https://www.datalumos.org/datalumos/project/9/version/V1/view"
                )
            )
        minimize.assert_called_once_with(checker)
        checker.goto.assert_called_once()

    def test_log_keeps_the_publish_request_body(self) -> None:
        """The trial log records method, path, status, and the JSON that was posted."""
        page = MagicMock()
        responses = [
            {"projectTitle": "Study"},
            {"depositAgreement": "text"},
            [],
            [{"id": 15, "name": "Public Domain Mark"}],
            {"success": True},
        ]

        def fake_request(*_args: object, **kwargs: object) -> dict:
            payload = responses.pop(0)
            return {"status": 200, "body": json.dumps(payload), "elapsedMs": 4}

        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "publish.jsonl"
            with patch(
                "publisher.DataLumosPublishClient.prepare_deposit_token",
                return_value="jwt",
            ), patch(
                "publisher.DataLumosPublishClient.deposit_request",
                side_effect=fake_request,
            ):
                DataLumosPublishClient(page, log_path=log_path).publish_project("9")
            lines = log_path.read_text(encoding="utf-8-sig").splitlines()
        posted = json.loads(lines[-1])
        self.assertEqual(posted["method"], "POST")
        self.assertEqual(posted["path"], "/deposit/publish")
        self.assertEqual(posted["status"], 200)
        body = json.loads(posted["requestBody"])
        self.assertEqual(body["licenseId"], "15")
        self.assertIs(body["agreed"], True)

    def test_saved_token_skips_opening_the_workspace(self) -> None:
        """A token kept from the previous project is sent as-is."""
        page = MagicMock()
        with patch(
            "publisher.DataLumosPublishClient.prepare_deposit_token"
        ) as prepare, patch(
            "publisher.DataLumosPublishClient.deposit_request",
            return_value={
                "status": 200,
                "body": '{"fileFolderUsed": 1, "storageUsedDisplay": "< 0.01 GB"}',
                "elapsedMs": 1,
            },
        ):
            DataLumosPublishClient(page, token="jwt").storage_status("9")
        prepare.assert_not_called()
        page.goto.assert_not_called()

    def test_rejected_token_is_forgotten(self) -> None:
        """A 401 clears the token so the next attempt can sign in."""
        client = DataLumosPublishClient(MagicMock(), token="jwt")
        with self.assertRaises(RuntimeError):
            client._accepted(
                "GET",
                "https://deposit.icpsr.umich.edu/deposit/viewStorage",
                {"status": 401, "body": "", "elapsedMs": 1},
            )
        self.assertEqual(client.token, "")

    def test_published_versions_reads_view_versions(self) -> None:
        """A public V1 is kept and an unpublished row is dropped."""
        page = MagicMock()

        def fake_request(*_args: object, **_kwargs: object) -> dict:
            payload = [
                {"versionLabel": "V1", "status": "PUBLISHED"},
                {"versionLabel": "V2", "status": "UNPUBLISHED"},
            ]
            return {"status": 200, "body": json.dumps(payload), "elapsedMs": 1}

        with patch(
            "publisher.DataLumosPublishClient.deposit_request",
            side_effect=fake_request,
        ) as request:
            labels = DataLumosPublishClient(page, token="jwt").published_versions("42")

        self.assertEqual(labels, ["V1"])
        url = str(request.call_args.args[3])
        self.assertIn("/deposit/viewVersions?", url)
        self.assertIn("path=%2Fdatalumos%2F42", url)
        page.goto.assert_not_called()


if __name__ == "__main__":
    unittest.main()
