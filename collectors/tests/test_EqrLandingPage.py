"""Tests for printing the EQR explanation page."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from collectors.EqrLandingPage import is_security_interstitial, pdf_is_security_interstitial, save_explanation_pdf
from collectors.EqrProjectRange import EXPLAIN_URL

_ARTICLE = """
<html><head><link rel="stylesheet" href="/theme.css">
<script>document.body.innerHTML = "kept"</script></head>
<body><h1>Electric Quarterly Reports (EQR)</h1></body></html>
"""
_INTERSTITIAL = "<html><title>Just a moment...</title><p>Performing security verification</p></html>"


class _Pages:
    """Records the HTML handed to the browser renderer."""

    def __init__(self) -> None:
        self.html = ""
        self.calls = 0

    def url_html_to_pdf(self, url: str, html: str, pdf_path: Path) -> bool:
        self.calls += 1
        self.html = html
        if url != EXPLAIN_URL:
            return False
        pdf_path.write_bytes(b"%PDF")
        return True


class TestEqrLandingPage(unittest.TestCase):
    """The saved page is the rendered article, not the browser security check."""

    def test_save_keeps_stylesheets_and_scripts(self) -> None:
        """CSS and script tags stay in the HTML the browser renders."""
        pages = _Pages()
        with tempfile.TemporaryDirectory() as tmp:
            save_explanation_pdf(pages, Path(tmp), _ARTICLE, lambda: _ARTICLE)
        self.assertIn("stylesheet", pages.html)
        self.assertIn("<script", pages.html)
        self.assertEqual(pages.calls, 1)

    def test_security_check_html_is_rejected(self) -> None:
        """The interstitial is not printed as the landing page."""
        self.assertTrue(is_security_interstitial(_INTERSTITIAL))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                save_explanation_pdf(_Pages(), Path(tmp), _INTERSTITIAL, lambda: _INTERSTITIAL)

    def test_existing_security_pdf_is_replaced(self) -> None:
        """A PDF whose text is the Cloudflare check is printed again."""
        pages = _Pages()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "landing_page.pdf"
            path.write_bytes(b"%PDF-1.4 Just a moment")
            self.assertTrue(pdf_is_security_interstitial(path))
            save_explanation_pdf(pages, Path(tmp), _ARTICLE, lambda: _ARTICLE)
            self.assertEqual(pages.calls, 1)
            path.write_bytes(b"%PDF-1.4 Electric Quarterly Reports")
            save_explanation_pdf(pages, Path(tmp), _ARTICLE, lambda: _ARTICLE)
            self.assertEqual(pages.calls, 1)


if __name__ == "__main__":
    unittest.main()
