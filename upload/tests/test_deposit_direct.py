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

    def test_workspace_html_without_a_token_returns_empty(self) -> None:
        """HTML that is not the deposit page does not invent a token."""
        page = MagicMock()
        response = MagicMock()
        response.status = 200
        response.text.return_value = "<html></html>"
        page.request.get.return_value = response
        self.assertEqual(workspace_html_token(page), "")
        page.evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
