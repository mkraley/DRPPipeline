"""Tests for the AirData download-page client."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from sourcing.AqsDownloadClient import AqsDownloadClient


class TestAqsDownloadClient(unittest.TestCase):
    """HTTP responses from the pre-generated files page."""

    def test_fetch_html_returns_the_body(self) -> None:
        """A 200 response returns the page text."""
        response = MagicMock(status_code=200, text="<html>files</html>")
        client = AqsDownloadClient(getter=lambda *_args, **_kwargs: response)
        self.assertEqual(client.fetch_html(), "<html>files</html>")

    def test_fetch_html_rejects_an_error_status(self) -> None:
        """A non-200 response raises RuntimeError."""
        response = MagicMock(status_code=503, text="")
        client = AqsDownloadClient(getter=lambda *_args, **_kwargs: response)
        with self.assertRaises(RuntimeError):
            client.fetch_html()


if __name__ == "__main__":
    unittest.main()
