"""
Unit tests for SocrataCollector.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from utils.Args import Args
from utils.Logger import Logger

from collectors.SocrataCollector import SocrataCollector
from collectors.test_utils import setup_mock_playwright


class TestSocrataCollector(unittest.TestCase):
    """Test cases for SocrataCollector class."""
    
    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        
        self.temp_dir = Path(tempfile.mkdtemp())
        # Mock Args.base_output_dir to use temp directory
        with patch.object(Args, 'base_output_dir', self.temp_dir):
            self.collector = SocrataCollector(headless=True)
    
    def tearDown(self) -> None:
        """Clean up after each test."""
        sys.argv = self._original_argv
        self.collector._cleanup_browser()
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)
    
    def test_init(self) -> None:
        """Test SocrataCollector initialization."""
        with patch.object(Args, 'base_output_dir', self.temp_dir):
            collector = SocrataCollector(headless=True)
            self.assertTrue(collector._headless)
            self.assertIsNone(collector._playwright)
            self.assertIsNone(collector._browser)
            self.assertIsNone(collector._page)
    
    
    def test_collect_invalid_url(self) -> None:
        """Test collect() with invalid URL."""
        result = self.collector.collect("not-a-url", 1)
        
        self.assertEqual(result['status'], "Invalid URL")
        self.assertIsNone(result['pdf_path'])
        self.assertIsNone(result['dataset_path'])
    
    @patch('utils.url_utils.requests.get')
    def test_collect_url_access_fails(self, mock_get: Mock) -> None:
        """Test collect() when URL access fails."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()
        
        result = self.collector.collect("https://example.com", 1)
        
        self.assertIn("Connection Error", result['status'])
        self.assertIsNone(result['pdf_path'])
    
    @patch('collectors.SocrataCollector.sync_playwright')
    @patch('utils.url_utils.requests.get')
    @patch('collectors.SocrataCollector.SocrataPageProcessor')
    @patch('collectors.SocrataCollector.SocrataMetadataExtractor')
    @patch('collectors.SocrataCollector.SocrataDatasetDownloader')
    def test_collect_success_mock(self, mock_downloader_cls: Mock, mock_extractor_cls: Mock, 
                                   mock_processor_cls: Mock, mock_get: Mock, mock_playwright: Mock) -> None:
        """Test collect() with mocked browser (basic flow)."""
        # Mock successful URL access
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        mock_page, _, _ = setup_mock_playwright(mock_playwright)

        # Mock page methods
        mock_page.goto.return_value = None
        mock_page.wait_for_timeout.return_value = None
        
        # Mock processor, downloader, and extractor
        mock_processor = mock_processor_cls.return_value
        mock_processor.generate_pdf.return_value = True
        
        mock_downloader = mock_downloader_cls.return_value
        mock_downloader.download.return_value = False  # Returns bool now
        
        mock_extractor = mock_extractor_cls.return_value
        mock_extractor.extract_all_metadata.return_value = {
            'title': None,
            'rows': None,
            'columns': None,
            'description': None,
            'keywords': None
        }
        
        result = self.collector.collect("https://data.cdc.gov/view/test", 1)
        
        # Should have attempted collection
        self.assertIsNotNone(result['status'])
        mock_page.goto.assert_called_once()
    
    def test_cleanup_browser_no_browser(self) -> None:
        """Test _cleanup_browser when no browser is initialized."""
        # Should not raise error
        self.collector._cleanup_browser()
        self.assertIsNone(self.collector._browser)
        self.assertIsNone(self.collector._playwright)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_init_browser_success(self, mock_playwright: Mock) -> None:
        """Test _init_browser successfully initializes browser."""
        setup_mock_playwright(mock_playwright)

        result = self.collector._init_browser()
        
        self.assertTrue(result)
        self.assertIsNotNone(self.collector._playwright)
        self.assertIsNotNone(self.collector._browser)
        self.assertIsNotNone(self.collector._page)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_init_browser_failure(self, mock_playwright: Mock) -> None:
        """Test _init_browser handles initialization failure."""
        mock_playwright.side_effect = Exception("Browser init failed")
        
        result = self.collector._init_browser()
        
        # Should return False and clean up on failure
        self.assertFalse(result)
        self.assertIsNone(self.collector._browser)
        self.assertIsNone(self.collector._playwright)

    def test_update_status(self) -> None:
        """Test _update_status appends when status exists, replaces when empty."""
        self.collector._result = {'status': None}
        self.collector._update_status('First')
        self.assertEqual(self.collector._result['status'], 'First')

        self.collector._update_status('Second')
        self.assertEqual(self.collector._result['status'], 'First; Second')

    @patch('collectors.SocrataCollector.create_output_folder', return_value=None)
    @patch('utils.url_utils.requests.get')
    def test_collect_output_folder_fails(self, mock_get: Mock, mock_create: Mock) -> None:
        """Test collect() when output folder creation fails."""
        mock_get.return_value = Mock(status_code=200)

        result = self.collector.collect("https://data.cdc.gov/view/x", 1)

        self.assertIn("Failed to create output folder", result['status'])
        self.assertIsNone(result['pdf_path'])
        self.assertIsNone(result['dataset_path'])

    @patch('collectors.SocrataCollector.sync_playwright')
    @patch('utils.url_utils.requests.get')
    def test_collect_page_load_fails(self, mock_get: Mock, mock_playwright: Mock) -> None:
        """Test collect() when browser loads URL but page.goto fails."""
        mock_get.return_value = Mock(status_code=200)

        mock_page, _, _ = setup_mock_playwright(mock_playwright)
        mock_page.goto.side_effect = Exception("Load failed")
        mock_page.wait_for_timeout.return_value = None

        with patch.object(Args, 'base_output_dir', self.temp_dir):
            result = self.collector.collect("https://data.cdc.gov/view/x", 1)

        self.assertIn("Failed to load page", result['status'])
        self.assertIsNone(result['pdf_path'])

