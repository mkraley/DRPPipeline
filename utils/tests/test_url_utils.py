"""
Unit tests for url_utils module.
"""

import sys
import unittest
from unittest.mock import Mock, patch

from utils.Args import Args
from utils.Logger import Logger
from utils import url_utils


class TestUrlUtils(unittest.TestCase):
    """Test cases for url_utils module."""
    
    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]

        Args.initialize()
        Logger.initialize(log_level="WARNING")
    
    def tearDown(self) -> None:
        """Clean up after each test."""
        sys.argv = self._original_argv
    
    def test_is_valid_url_valid_http(self) -> None:
        """Test is_valid_url with valid HTTP URL."""
        self.assertTrue(url_utils.is_valid_url("http://example.com"))
    
    def test_is_valid_url_valid_https(self) -> None:
        """Test is_valid_url with valid HTTPS URL."""
        self.assertTrue(url_utils.is_valid_url("https://example.com"))
    
    def test_is_valid_url_invalid_empty(self) -> None:
        """Test is_valid_url with empty string."""
        self.assertFalse(url_utils.is_valid_url(""))
    
    def test_is_valid_url_invalid_none(self) -> None:
        """Test is_valid_url with None."""
        self.assertFalse(url_utils.is_valid_url(None))
    
    def test_is_valid_url_invalid_no_protocol(self) -> None:
        """Test is_valid_url with URL missing protocol."""
        self.assertFalse(url_utils.is_valid_url("example.com"))
    
    def test_is_valid_url_invalid_ftp(self) -> None:
        """Test is_valid_url with FTP URL (not HTTP/HTTPS)."""
        self.assertFalse(url_utils.is_valid_url("ftp://example.com"))
    
    @patch('utils.url_utils.requests.get')
    def test_access_url_success(self, mock_get) -> None:
        """Test access_url with successful response."""
        from unittest.mock import Mock
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        success, status = url_utils.access_url("https://example.com")
        
        self.assertTrue(success)
        self.assertEqual(status, "Success")
        mock_get.assert_called_once_with(
            "https://example.com",
            timeout=30,
            allow_redirects=True,
            headers=url_utils.BROWSER_HEADERS,
        )
    
    @patch('utils.url_utils.requests.get')
    def test_access_url_http_error(self, mock_get) -> None:
        """Test access_url with HTTP error."""
        from unittest.mock import Mock
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        success, status = url_utils.access_url("https://example.com")
        
        self.assertFalse(success)
        self.assertEqual(status, "HTTP 404")
    
    @patch('utils.url_utils.requests.get')
    def test_access_url_timeout(self, mock_get) -> None:
        """Test access_url with timeout."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()
        
        success, status = url_utils.access_url("https://example.com")
        
        self.assertFalse(success)
        self.assertEqual(status, "Timeout")
    
    @patch('utils.url_utils.requests.get')
    def test_access_url_connection_error(self, mock_get) -> None:
        """Test access_url with connection error."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()
        
        success, status = url_utils.access_url("https://example.com")
        
        self.assertFalse(success)
        self.assertEqual(status, "Connection Error")

    def test_infer_file_type_from_url(self) -> None:
        """Test infer_file_type prefers URL path extension."""
        self.assertEqual(url_utils.infer_file_type("https://example.com/data.csv"), "csv")
        self.assertEqual(url_utils.infer_file_type("https://example.com/path/file.json"), "json")
        self.assertEqual(url_utils.infer_file_type("https://example.com/archive.zip"), "zip")

    def test_infer_file_type_from_content_type(self) -> None:
        """Test infer_file_type uses Content-Type when URL has no extension."""
        self.assertEqual(
            url_utils.infer_file_type("https://example.com/api", "text/csv"),
            "csv",
        )
        self.assertEqual(
            url_utils.infer_file_type("https://example.com/api", "application/json"),
            "json",
        )
        self.assertEqual(
            url_utils.infer_file_type(
                "https://example.com/api",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            "xlsx",
        )

    def test_infer_file_type_url_over_content_type(self) -> None:
        """Test infer_file_type prefers URL over Content-Type."""
        self.assertEqual(
            url_utils.infer_file_type("https://example.com/data.csv", "text/plain"),
            "csv",
        )

    def test_infer_file_type_unknown(self) -> None:
        """Test infer_file_type returns unknown when no info available."""
        self.assertEqual(url_utils.infer_file_type("https://example.com/noext"), "unknown")

    @patch('utils.url_utils.requests.head')
    def test_fetch_url_head_success(self, mock_head: Mock) -> None:
        """Test fetch_url_head returns status, content-type, and None error on success."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/csv; charset=utf-8"}
        mock_head.return_value = mock_response

        status, ct, err = url_utils.fetch_url_head("https://example.com/data.csv")

        self.assertEqual(status, 200)
        self.assertEqual(ct, "text/csv")
        self.assertIsNone(err)
        mock_head.assert_called_once_with(
            "https://example.com/data.csv",
            timeout=30,
            allow_redirects=True,
        )

    @patch('utils.url_utils.requests.head')
    def test_fetch_url_head_404(self, mock_head: Mock) -> None:
        """Test fetch_url_head returns 404, None content-type, None error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.headers = {}
        mock_head.return_value = mock_response

        status, ct, err = url_utils.fetch_url_head("https://example.com/missing")

        self.assertEqual(status, 404)
        self.assertIsNone(ct)
        self.assertIsNone(err)

    @patch('utils.url_utils.requests.head')
    def test_fetch_url_head_exception(self, mock_head: Mock) -> None:
        """Test fetch_url_head returns -1, None, and exception message on exception."""
        mock_head.side_effect = Exception("Network error")

        status, ct, err = url_utils.fetch_url_head("https://example.com/x")

        self.assertEqual(status, -1)
        self.assertIsNone(ct)
        self.assertEqual(err, "Network error")

    @patch('utils.url_utils.requests.head')
    def test_fetch_url_head_exception_with_cause(self, mock_head: Mock) -> None:
        """Test fetch_url_head returns exception cause when present."""
        cause = ConnectionError("Connection refused")
        outer = OSError("failed")
        outer.__cause__ = cause
        mock_head.side_effect = outer

        status, ct, err = url_utils.fetch_url_head("https://example.com/x")

        self.assertEqual(status, -1)
        self.assertIsNone(ct)
        self.assertEqual(err, "Connection refused")

    @patch('utils.url_utils.requests.head')
    def test_fetch_url_head_connection_error_treated_as_404(
        self, mock_head: Mock
    ) -> None:
        """Test 'Failed to establish a new connection' returns 404."""
        mock_head.side_effect = Exception(
            "Failed to establish a new connection: [Errno 111] Connection refused"
        )

        status, ct, err = url_utils.fetch_url_head("https://example.com/x")

        self.assertEqual(status, 404)
        self.assertIsNone(ct)
        self.assertIn("Connection refused", err)

    @patch('utils.url_utils.requests.get')
    @patch('utils.url_utils.requests.head')
    def test_fetch_url_head_html_not_found_page(
        self, mock_head: Mock, mock_get: Mock
    ) -> None:
        """Test 200 HTML with 'page not found' in body returns 404."""
        mock_head_resp = Mock()
        mock_head_resp.status_code = 200
        mock_head_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_head.return_value = mock_head_resp

        mock_get_resp = Mock()
        mock_get_resp.raw = Mock()
        mock_get_resp.raw.read.return_value = (
            b"<html><body>Sorry, the page you requested could not be found.</body></html>"
        )
        mock_get_resp.raw.decode_content = True
        mock_get.return_value = mock_get_resp

        status, ct, err = url_utils.fetch_url_head("https://example.com/missing")

        self.assertEqual(status, 404)
        self.assertIsNone(ct)
        self.assertIsNone(err)
        mock_get.assert_called_once()

    @patch('utils.url_utils.requests.get')
    @patch('utils.url_utils.requests.head')
    def test_fetch_url_head_html_ok_page(
        self, mock_head: Mock, mock_get: Mock
    ) -> None:
        """Test 200 HTML without not-found phrases returns 200."""
        mock_head_resp = Mock()
        mock_head_resp.status_code = 200
        mock_head_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_head.return_value = mock_head_resp

        mock_get_resp = Mock()
        mock_get_resp.raw = Mock()
        mock_get_resp.raw.read.return_value = (
            b"<html><body>Dataset download page with actual data</body></html>"
        )
        mock_get_resp.raw.decode_content = True
        mock_get.return_value = mock_get_resp

        status, ct, err = url_utils.fetch_url_head("https://example.com/page")

        self.assertEqual(status, 200)
        self.assertEqual(ct, "text/html")
        self.assertIsNone(err)
