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
            headers=url_utils.BROWSER_HEADERS,
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

    def test_body_looks_like_not_found_true(self) -> None:
        """Test body_looks_like_not_found returns True for not-found phrases."""
        self.assertTrue(
            url_utils.body_looks_like_not_found(
                "<html><body>Sorry, the page you requested could not be found.</body></html>"
            )
        )
        self.assertTrue(
            url_utils.body_looks_like_not_found("PAGE NOT FOUND")
        )

    def test_body_looks_like_not_found_false(self) -> None:
        """Test body_looks_like_not_found returns False for normal content."""
        self.assertFalse(
            url_utils.body_looks_like_not_found("<html><body>Dataset download</body></html>")
        )
        self.assertFalse(url_utils.body_looks_like_not_found(""))

    def test_body_looks_like_not_found_false_for_large_page(self) -> None:
        """Large pages with phrase in template/script are not false positives (e.g. datadiscovery.nlm.nih.gov)."""
        # Valid dataset page that incidentally contains "page not found" somewhere - should not be flagged
        large_body = "x" * 20000 + "page not found" + "y" * 1000
        self.assertFalse(url_utils.body_looks_like_not_found(large_body))

    @patch("utils.url_utils.requests.get")
    def test_fetch_page_body_success(self, mock_get: Mock) -> None:
        """Test fetch_page_body returns 200, body, content-type, and False for logical 404."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b"<html><body>OK</body></html>"
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_get.return_value = mock_resp

        status, body, ct, is_logical = url_utils.fetch_page_body("https://example.com/page")

        self.assertEqual(status, 200)
        self.assertEqual(body, "<html><body>OK</body></html>")
        self.assertEqual(ct, "text/html")
        self.assertFalse(is_logical)
        expected_headers = {**url_utils.BROWSER_HEADERS, "Accept-Encoding": "gzip, deflate"}
        mock_get.assert_called_once_with(
            "https://example.com/page",
            timeout=30,
            allow_redirects=True,
            headers=expected_headers,
        )

    @patch("utils.url_utils.requests.get")
    def test_fetch_page_body_http_404(self, mock_get: Mock) -> None:
        """Test fetch_page_body returns 404, body, and is_logical_404 False for HTTP 404."""
        mock_resp = Mock()
        mock_resp.status_code = 404
        mock_resp.content = b"<html><body>Not found</body></html>"
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_get.return_value = mock_resp

        status, body, ct, is_logical = url_utils.fetch_page_body("https://example.com/missing")

        self.assertEqual(status, 404)
        self.assertIn("Not found", body)
        self.assertFalse(is_logical)

    @patch("utils.url_utils.requests.get")
    def test_fetch_page_body_logical_404(self, mock_get: Mock) -> None:
        """Test fetch_page_body returns 404 and is_logical_404 True for 200 HTML with not-found body."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = (
            b"<html><body>Sorry, the page you requested could not be found.</body></html>"
        )
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_get.return_value = mock_resp

        status, body, ct, is_logical = url_utils.fetch_page_body("https://example.com/ghost")

        self.assertEqual(status, 404)
        self.assertTrue(is_logical)
        self.assertEqual(ct, "text/html")

    @patch("utils.url_utils.requests.get")
    def test_fetch_page_body_connection_error_as_404(self, mock_get: Mock) -> None:
        """Test connection error returns 404, empty body, is_logical_404 False."""
        mock_get.side_effect = ConnectionError(
            "Failed to establish a new connection: [Errno 111] Connection refused"
        )

        status, body, ct, is_logical = url_utils.fetch_page_body("https://example.com/x")

        self.assertEqual(status, 404)
        self.assertEqual(body, "")
        self.assertIsNone(ct)
        self.assertFalse(is_logical)

    @patch("utils.url_utils.requests.get")
    def test_fetch_page_body_other_exception(self, mock_get: Mock) -> None:
        """Test other exception returns -1, empty body."""
        mock_get.side_effect = Exception("Timeout")

        status, body, ct, is_logical = url_utils.fetch_page_body("https://example.com/x")

        self.assertEqual(status, -1)
        self.assertEqual(body, "")
        self.assertIsNone(ct)
        self.assertFalse(is_logical)

    @patch("utils.url_utils.requests.get")
    def test_fetch_page_body_binary_content_returns_empty_body(self, mock_get: Mock) -> None:
        """Test binary Content-Type returns empty body to avoid decoded garbage."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x00\x01\x02PDF\xff\xfe"
        mock_resp.headers = {"Content-Type": "application/pdf"}
        mock_get.return_value = mock_resp

        status, body, ct, is_logical = url_utils.fetch_page_body("https://example.com/doc.pdf")

        self.assertEqual(status, 200)
        self.assertEqual(body, "")
        self.assertEqual(ct, "application/pdf")
        self.assertFalse(is_logical)

    @patch("utils.url_utils.requests.get")
    def test_fetch_page_body_gzip_magic_returns_empty_body(self, mock_get: Mock) -> None:
        """Test gzip magic bytes (mis-labeled as text) returns empty body."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x1f\x8b\x08\x00" + b"x" * 100
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_get.return_value = mock_resp

        status, body, ct, is_logical = url_utils.fetch_page_body("https://example.com/page")

        self.assertEqual(status, 200)
        self.assertEqual(body, "")
        self.assertEqual(ct, "text/html")

    @patch("utils.url_utils.requests.get")
    def test_fetch_page_body_decoded_garbage_returns_empty_body(self, mock_get: Mock) -> None:
        """Test decoded body with few printable chars is treated as garbage and cleared."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.content = (
            b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
            b"\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f"
            b"xyz"
        )
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_get.return_value = mock_resp

        status, body, ct, is_logical = url_utils.fetch_page_body("https://example.com/page")

        self.assertEqual(status, 200)
        self.assertEqual(body, "")
        self.assertEqual(ct, "text/html")


class TestIsNonHtmlResponse(unittest.TestCase):
    """Tests for is_non_html_response (used for download button on non-HTML links)."""

    def test_pdf_content_type_is_non_html(self) -> None:
        self.assertTrue(url_utils.is_non_html_response("application/pdf", ""))

    def test_xml_content_type_is_non_html(self) -> None:
        self.assertTrue(url_utils.is_non_html_response("application/xml", ""))

    def test_zip_content_type_is_non_html(self) -> None:
        self.assertTrue(url_utils.is_non_html_response("application/zip", ""))

    def test_html_content_type_with_html_body_is_html(self) -> None:
        self.assertFalse(url_utils.is_non_html_response("text/html", "<html><body>Hi</body></html>"))

    def test_xml_content_type_with_html_body_is_html(self) -> None:
        """NCBI BioSample etc.: served as XML but body has <html>."""
        self.assertFalse(url_utils.is_non_html_response("application/xml", "<!DOCTYPE html><html><body></body></html>"))

    def test_xml_body_sniffing_is_non_html(self) -> None:
        self.assertTrue(url_utils.is_non_html_response("text/plain", "<?xml version='1.0'?>"))

    def test_raw_magic_bytes_overrides_content_type(self) -> None:
        self.assertTrue(url_utils.is_non_html_response("text/html", "", raw_bytes=b"%PDF-1.4"))

    def test_json_content_type_is_html(self) -> None:
        """JSON is displayable as text, not offered as download."""
        self.assertFalse(url_utils.is_non_html_response("application/json", '{"a":1}'))


class TestWafChallenge(unittest.TestCase):
    """Tests for is_waf_challenge (AWS WAF detection). Body must be >= 100 chars."""

    def test_javascript_disabled_detected(self) -> None:
        body = "<noscript>JavaScript is disabled. Please enable it.</noscript>" + " " * 50
        self.assertTrue(url_utils.is_waf_challenge(202, body))

    def test_javascript_not_enabled_detected(self) -> None:
        body = "<noscript>JavaScript is not enabled. Enable JavaScript to continue.</noscript>" + " " * 50
        self.assertTrue(url_utils.is_waf_challenge(202, body))

    def test_enable_javascript_detected(self) -> None:
        body = "<noscript>Please enable JavaScript to continue.</noscript>" + " " * 60
        self.assertTrue(url_utils.is_waf_challenge(200, body))

    def test_awswaf_detected(self) -> None:
        self.assertTrue(url_utils.is_waf_challenge(202, "x" * 100 + "awswaf challenge"))

    def test_normal_html_not_detected(self) -> None:
        body = "<html><body><h1>Normal page</h1><noscript>Fallback</noscript></body></html>" + " " * 30
        self.assertFalse(url_utils.is_waf_challenge(200, body))


class TestResolveCatalogResourceUrl(unittest.TestCase):
    """Tests for resolve_catalog_resource_url."""

    @patch("utils.url_utils.fetch_page_body")
    def test_returns_res_url_href_when_present(self, mock_fetch: Mock) -> None:
        """When HTML contains <a id=\"res_url\" href=\"...\">, returns that href."""
        mock_fetch.return_value = (
            200,
            '<html><body><a id="res_url" href="https://data.example.com/file.csv">Download</a></body></html>',
            "text/html",
            False,
        )
        result = url_utils.resolve_catalog_resource_url("https://catalog.data.gov/dataset/x/resource/y")
        self.assertEqual(result, "https://data.example.com/file.csv")

    @patch("utils.url_utils.fetch_page_body")
    def test_returns_none_for_non_catalog_url(self, mock_fetch: Mock) -> None:
        """Non-catalog URL returns None without calling fetch."""
        result = url_utils.resolve_catalog_resource_url("https://example.com/page")
        self.assertIsNone(result)
        mock_fetch.assert_not_called()

    @patch("utils.url_utils.fetch_page_body")
    def test_returns_none_for_404(self, mock_fetch: Mock) -> None:
        """404 or logical 404 returns None."""
        mock_fetch.return_value = (404, "Not found", "text/html", False)
        result = url_utils.resolve_catalog_resource_url("https://catalog.data.gov/dataset/x/resource/y")
        self.assertIsNone(result)

    @patch("utils.url_utils.fetch_page_body")
    def test_returns_none_when_res_url_missing(self, mock_fetch: Mock) -> None:
        """When #res_url is missing from HTML, returns None."""
        mock_fetch.return_value = (200, "<html><body>No link here</body></html>", "text/html", False)
        result = url_utils.resolve_catalog_resource_url("https://catalog.data.gov/dataset/x/resource/y")
        self.assertIsNone(result)
