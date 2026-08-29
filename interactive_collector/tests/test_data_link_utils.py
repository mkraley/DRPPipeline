"""
Unit tests for data_link_utils (batch download link extraction).
"""

import unittest

from interactive_collector.data_link_utils import (
    extract_data_links_from_html,
    filter_urls_not_in_scoreboard,
    is_data_file_url,
)


class TestIsDataFileUrl(unittest.TestCase):
    """Tests for is_data_file_url."""

    def test_pdf_and_csv(self) -> None:
        """PDF and CSV URLs are data files."""
        self.assertTrue(is_data_file_url("https://example.com/a/file.pdf"))
        self.assertTrue(is_data_file_url("https://example.com/data.csv?x=1"))

    def test_html_not_data(self) -> None:
        """HTML pages are not data files."""
        self.assertFalse(is_data_file_url("https://example.com/page.html"))
        self.assertFalse(is_data_file_url("https://example.com/about"))


class TestExtractDataLinksFromHtml(unittest.TestCase):
    """Tests for extract_data_links_from_html."""

    def test_excludes_header_footer_links(self) -> None:
        """Links in header/footer are omitted; main content links kept."""
        html = """
        <html><body>
        <header><a href="/nav.pdf">Nav PDF</a></header>
        <main>
          <a href="/files/one.csv">One</a>
          <a href="https://cdn.example.org/two.zip">Two</a>
        </main>
        <footer><a href="/footer.pdf">Footer PDF</a></footer>
        </body></html>
        """
        links = extract_data_links_from_html(html, "https://www.example.com/catalog")
        self.assertIn("https://www.example.com/files/one.csv", links)
        self.assertIn("https://cdn.example.org/two.zip", links)
        self.assertEqual(len(links), 2)

    def test_ignores_non_data_links(self) -> None:
        """Non-data hrefs in main are skipped."""
        html = '<main><a href="/page">Page</a><a href="/x.pdf">Doc</a></main>'
        links = extract_data_links_from_html(html, "https://example.com/")
        self.assertEqual(links, ["https://example.com/x.pdf"])


class TestFilterUrlsNotInScoreboard(unittest.TestCase):
    """Tests for filter_urls_not_in_scoreboard."""

    def test_filters_existing(self) -> None:
        """URLs on the scoreboard are removed."""
        urls = ["https://a.com/1.pdf", "https://a.com/2.pdf"]
        out = filter_urls_not_in_scoreboard(urls, {"https://a.com/1.pdf"})
        self.assertEqual(out, ["https://a.com/2.pdf"])


if __name__ == "__main__":
    unittest.main()
