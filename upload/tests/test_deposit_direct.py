"""Unit tests for reading the deposit token without rendering the workspace."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from utils.Logger import Logger

from upload.deposit_direct import prepare_deposit_token, workspace_html_token

_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signaturepart"


class TestDepositDirect(unittest.TestCase):
    """Token sources, in order: the open page, workspace HTML, then a render."""

    def setUp(self) -> None:
        """Logger is required when a source is chosen."""
        Logger.initialize(log_level="ERROR", log_file=False)

    def test_page_token_skips_the_workspace(self) -> None:
        """A token already defined on the page is used as-is."""
        page = MagicMock()
        page.evaluate.return_value = _TOKEN
        token = prepare_deposit_token(page)
        self.assertEqual(token, _TOKEN)
        page.goto.assert_not_called()
        page.request.get.assert_not_called()

    def test_workspace_html_installs_the_token_without_navigation(self) -> None:
        """The inline assignment is copied onto the page and not logged."""
        page = MagicMock()
        page.evaluate.side_effect = ["", None]
        response = MagicMock()
        response.status = 200
        response.text.return_value = f"var jwtToken = '{_TOKEN}';"
        page.request.get.return_value = response
        token = prepare_deposit_token(page)
        self.assertEqual(token, _TOKEN)
        page.goto.assert_not_called()
        page.evaluate.assert_any_call(
            """(token) => { window.jwtToken = token; }""",
            _TOKEN,
        )

    def test_missing_html_token_renders_the_workspace(self) -> None:
        """A login page with no token falls back to opening the workspace."""
        page = MagicMock()
        page.evaluate.side_effect = ["", None, _TOKEN]
        response = MagicMock()
        response.status = 200
        response.text.return_value = "<html>sign in</html>"
        page.request.get.return_value = response
        with patch("upload.DataLumosAuthenticator.wait_for_human_verification"):
            token = prepare_deposit_token(page)
        self.assertEqual(token, _TOKEN)
        page.goto.assert_called_once()
        waited_for = page.wait_for_function.call_args.args[0]
        self.assertIn("jwtToken", waited_for)
        self.assertNotIn("$.ajax", waited_for)
        self.assertEqual(page.wait_for_function.call_args.kwargs["timeout"], 300000)

    def test_document_token_skips_the_script_wait(self) -> None:
        """A token already in the loaded document is used without waiting for script."""
        page = MagicMock()
        page.evaluate.side_effect = ["", None, None, _TOKEN]
        page.content.return_value = f"var jwtToken = '{_TOKEN}';"
        response = MagicMock()
        response.status = 200
        response.text.return_value = "<html>sign in</html>"
        page.request.get.return_value = response
        with patch("upload.DataLumosAuthenticator.wait_for_human_verification"):
            token = prepare_deposit_token(page)
        self.assertEqual(token, _TOKEN)
        page.wait_for_function.assert_not_called()
        page.evaluate.assert_any_call(
            """(token) => { window.jwtToken = token; }""",
            _TOKEN,
        )

    def test_workspace_html_without_a_token_returns_empty(self) -> None:
        """HTML that is not the deposit page does not invent a token."""
        page = MagicMock()
        response = MagicMock()
        response.status = 200
        response.text.return_value = "<html></html>"
        page.request.get.return_value = response
        self.assertEqual(workspace_html_token(page), "")
        page.evaluate.assert_not_called()


class TestDepositRequestBody(unittest.TestCase):
    """JSON publish bodies use the request data, not a form."""

    def test_json_body_is_posted_as_data(self) -> None:
        """A publish body is sent as JSON data."""
        from upload.deposit_direct import deposit_request

        page = MagicMock()
        response = MagicMock()
        response.status = 200
        response.text.return_value = '{"ok": true}'
        page.request.post.return_value = response

        deposit_request(
            page,
            "jwt",
            "POST",
            "https://deposit.icpsr.umich.edu/deposit/publish",
            content_type="application/json",
            body='{"agreed": true}',
        )

        kwargs = page.request.post.call_args.kwargs
        self.assertEqual(kwargs["data"], '{"agreed": true}')
        self.assertNotIn("form", kwargs)
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")

    def test_delete_uses_fetch_method(self) -> None:
        """DELETE /deletePath is sent with method DELETE, not POST."""
        from upload.deposit_direct import deposit_request

        page = MagicMock()
        response = MagicMock()
        response.status = 200
        response.text.return_value = ""
        page.request.fetch.return_value = response

        deposit_request(
            page,
            "jwt",
            "DELETE",
            "https://deposit.icpsr.umich.edu/deposit/deletePath?path=%2Fdatalumos%2F1",
        )

        kwargs = page.request.fetch.call_args.kwargs
        self.assertEqual(kwargs["method"], "DELETE")
        page.request.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
