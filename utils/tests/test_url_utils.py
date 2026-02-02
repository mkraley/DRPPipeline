"""
Unit tests for url_utils module.
"""

import sys
import unittest
from unittest.mock import patch

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
            allow_redirects=True
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
