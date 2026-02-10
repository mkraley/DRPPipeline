"""
Unit tests for the Interactive Collector Flask app.
"""

import unittest
from unittest.mock import patch

from interactive_collector.app import app, _status_label


class TestStatusLabel(unittest.TestCase):
    """Tests for _status_label helper."""

    def test_ok(self) -> None:
        """Test 200 returns OK."""
        self.assertEqual(_status_label(200, False), "OK")

    def test_404(self) -> None:
        """Test 404 without logical returns 404."""
        self.assertEqual(_status_label(404, False), "404")

    def test_404_logical(self) -> None:
        """Test 404 with logical returns 404 (logical)."""
        self.assertEqual(_status_label(404, True), "404 (logical)")

    def test_error(self) -> None:
        """Test negative status returns Error (code)."""
        self.assertEqual(_status_label(-1, False), "Error (-1)")


class TestAppRoutes(unittest.TestCase):
    """Tests for Flask app routes."""

    def setUp(self) -> None:
        """Create test client."""
        self.client = app.test_client()

    def test_index_no_url_returns_form(self) -> None:
        """GET / with no url param returns form without result."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Interactive Collector", response.data)
        self.assertIn(b"name=\"url\"", response.data)
        self.assertIn(b"Fetch", response.data)
        self.assertNotIn(b"Result", response.data)

    def test_index_invalid_url_returns_message(self) -> None:
        """GET / with invalid url shows Invalid URL and message."""
        response = self.client.get("/", query_string={"url": "not-a-url"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid URL", response.data)
        self.assertIn(b"valid http", response.data)

    @patch("interactive_collector.app.fetch_page_body")
    def test_index_valid_url_shows_result(
        self, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """GET / with valid url fetches and shows status and body."""
        mock_fetch_page_body.return_value = (
            200,
            "<html><body>Hello</body></html>",
            "text/html",
            False,
        )
        response = self.client.get(
            "/", query_string={"url": "https://example.com"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Result", response.data)
        self.assertIn(b"OK", response.data)
        self.assertIn(b"https://example.com", response.data)
        self.assertIn(b"<iframe", response.data)
        self.assertIn(b"srcdoc=", response.data)
        self.assertIn(b"Hello", response.data)
        mock_fetch_page_body.assert_called_once_with("https://example.com")

    @patch("interactive_collector.app.fetch_page_body")
    def test_index_404_shows_status(
        self, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """GET / when fetch returns 404 shows 404 status."""
        mock_fetch_page_body.return_value = (
            404,
            "Not found",
            "text/html",
            False,
        )
        response = self.client.get(
            "/", query_string={"url": "https://example.com/missing"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"404", response.data)
        self.assertNotIn(b"404 (logical)", response.data)

    @patch("interactive_collector.app.fetch_page_body")
    def test_index_logical_404_shows_label(
        self, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """GET / when fetch returns logical 404 shows 404 (logical)."""
        mock_fetch_page_body.return_value = (
            404,
            "<html>page not found</html>",
            "text/html",
            True,
        )
        response = self.client.get(
            "/", query_string={"url": "https://example.com/ghost"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"404 (logical)", response.data)

    @patch("interactive_collector.app.fetch_page_body")
    def test_index_binary_content_shows_message_not_body(
        self, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """GET / with binary Content-Type shows message instead of body."""
        mock_fetch_page_body.return_value = (
            200,
            "",
            "application/pdf",
            False,
        )
        response = self.client.get(
            "/", query_string={"url": "https://example.com/file.pdf"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Binary content (application/pdf). Not displayed.", response.data)
        self.assertNotIn(b"<iframe", response.data)
