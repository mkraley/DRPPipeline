"""Tests for IRMA HTML DownloadFile rejection diagnostics."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from collectors.NpsHtmlDownloadCheck import (
    is_allowed_html_filename,
    unexpected_html_message,
)


class TestNpsHtmlDownloadCheck(unittest.TestCase):
    """Tests for unexpected HTML bodies on Digital File URLs."""

    def test_rhtml_is_allowed(self) -> None:
        """R Markdown HTML sidecars are real Digital Files."""
        self.assertTrue(is_allowed_html_filename("AboutExceedances.Rhtml"))

    def test_pdf_html_body_reports_redirect_and_title(self) -> None:
        """Non-HTML names that receive an IRMA app page get a detailed message."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.pdf"
            path.write_bytes(
                b"<!DOCTYPE html><html><head><title>IRMA DataStore</title></head>"
                b"<body>home</body></html>"
            )
            message = unexpected_html_message(
                path,
                filename="report.pdf",
                url="https://irma.nps.gov/DataStore/DownloadFile/1",
                status_code=200,
                content_type="text/html; charset=utf-8",
                final_url="https://irma.nps.gov/DataStore/",
            )
        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("HTTP 200", message)
        self.assertIn("text/html", message)
        self.assertIn("redirected to", message)
        self.assertIn("IRMA home/app page", message)
        self.assertIn("IRMA DataStore", message)
        self.assertIn("DownloadFile/1", message)
        self.assertIn(" | ", message)

    def test_html_filename_is_kept(self) -> None:
        """A .html Digital File is not treated as a login page."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"
            path.write_bytes(b"<!DOCTYPE html><html><body>ok</body></html>")
            self.assertIsNone(
                unexpected_html_message(
                    path,
                    filename="report.html",
                    url="https://irma.nps.gov/DataStore/DownloadFile/2",
                )
            )


if __name__ == "__main__":
    unittest.main()
