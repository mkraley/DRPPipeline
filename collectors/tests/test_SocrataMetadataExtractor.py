"""
Unit tests for SocrataMetadataExtractor.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from utils.Args import Args
from utils.Logger import Logger

from collectors.SocrataCollector import SocrataCollector
from collectors.SocrataMetadataExtractor import SocrataMetadataExtractor
from collectors.tests.test_utils import setup_mock_playwright


class TestSocrataMetadataExtractor(unittest.TestCase):
    """Test cases for SocrataMetadataExtractor class."""
    
    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        
        self.temp_dir = Path(tempfile.mkdtemp())
        with patch.object(Args, "base_output_dir", self.temp_dir):
            self.collector = SocrataCollector(headless=True)
            self.collector._result = {}
            self.extractor = SocrataMetadataExtractor(self.collector)
    
    def tearDown(self) -> None:
        """Clean up after each test."""
        sys.argv = self._original_argv
        self.collector._cleanup_browser()
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)
    
    def test_init(self) -> None:
        """Test SocrataMetadataExtractor initialization."""
        with patch.object(Args, 'base_output_dir', self.temp_dir):
            collector = SocrataCollector(headless=True)
            extractor = SocrataMetadataExtractor(collector)
            self.assertEqual(extractor._collector, collector)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_extract_title_success(self, mock_playwright: Mock) -> None:
        """Test _extract_title extracts title from h2.asset-name."""
        mock_page, _, _ = setup_mock_playwright(mock_playwright)
        mock_locator = Mock()

        self.collector._init_browser()
        extractor = SocrataMetadataExtractor(self.collector)

        mock_page.locator.return_value = mock_locator
        mock_locator.count.return_value = 1
        mock_locator.first.inner_text.return_value = "  Test Dataset Title  "
        
        result = extractor._extract_title()
        
        self.assertEqual(result, "Test Dataset Title")
        mock_page.locator.assert_called_with('h2.asset-name')
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_extract_title_not_found(self, mock_playwright: Mock) -> None:
        """Test _extract_title returns None when title not found."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        mock_locator = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        extractor = SocrataMetadataExtractor(self.collector)
        
        mock_page.locator.return_value = mock_locator
        mock_locator.count.return_value = 0
        
        result = extractor._extract_title()
        
        self.assertIsNone(result)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_extract_title_exception(self, mock_playwright: Mock) -> None:
        """Test _extract_title handles exceptions."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        extractor = SocrataMetadataExtractor(self.collector)
        
        mock_page.locator.side_effect = Exception("Error")
        
        result = extractor._extract_title()
        
        self.assertIsNone(result)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_extract_dataset_metadata_success(self, mock_playwright: Mock) -> None:
        """Test _extract_dataset_metadata extracts rows and columns."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        mock_metadata_row = Mock()
        mock_pairs = Mock()
        mock_pair = Mock()
        mock_key = Mock()
        mock_value = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        extractor = SocrataMetadataExtractor(self.collector)
        
        # page.locator is only used for 'dl.metadata-row'; .metadata-pair and
        # .metadata-pair-key/value are used via metadata_row.locator and pair.locator
        mock_page.locator.return_value = mock_metadata_row
        mock_metadata_row.count.return_value = 1
        mock_metadata_row.locator.return_value = mock_pairs
        mock_pairs.count.return_value = 2
        mock_pairs.nth.return_value = mock_pair
        # pair.locator is called 4 times (key, value for each of 2 pairs)
        mock_pair.locator.side_effect = [mock_key, mock_value, mock_key, mock_value]
        mock_key.count.return_value = 1
        mock_value.count.return_value = 1
        
        # First pair: Rows, second pair: Columns
        mock_key.first.inner_text.side_effect = ["Rows", "Columns"]
        mock_value.first.inner_text.side_effect = ["1000", "25"]
        
        rows, columns = extractor._extract_dataset_metadata()
        
        self.assertEqual(rows, "1000")
        self.assertEqual(columns, "25")
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_extract_dataset_metadata_not_found(self, mock_playwright: Mock) -> None:
        """Test _extract_dataset_metadata returns None when metadata not found."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        mock_metadata_row = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        extractor = SocrataMetadataExtractor(self.collector)
        
        mock_page.locator.return_value = mock_metadata_row
        mock_metadata_row.count.return_value = 0
        
        rows, columns = extractor._extract_dataset_metadata()
        
        self.assertIsNone(rows)
        self.assertIsNone(columns)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_extract_description_success(self, mock_playwright: Mock) -> None:
        """Test _extract_description extracts HTML description."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        mock_locator = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        extractor = SocrataMetadataExtractor(self.collector)
        
        mock_page.locator.return_value = mock_locator
        mock_locator.count.return_value = 1
        mock_locator.first.inner_html.return_value = "  <p>Test description with <strong>rich text</strong></p>  "
        
        result = extractor._extract_description()
        
        self.assertEqual(result, "<p>Test description with <strong>rich text</strong></p>")
        mock_page.locator.assert_called_with('div.description-section')
        mock_locator.first.inner_html.assert_called_once()
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_extract_description_not_found(self, mock_playwright: Mock) -> None:
        """Test _extract_description returns None when not found."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        mock_locator = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        extractor = SocrataMetadataExtractor(self.collector)
        
        mock_page.locator.return_value = mock_locator
        mock_locator.count.return_value = 0
        
        result = extractor._extract_description()
        
        self.assertIsNone(result)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_extract_keywords_success(self, mock_playwright: Mock) -> None:
        """Test _extract_keywords extracts keywords from metadata table."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        mock_tables = Mock()
        mock_table = Mock()
        mock_h3 = Mock()
        mock_rows = Mock()
        mock_row = Mock()
        mock_tds = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        extractor = SocrataMetadataExtractor(self.collector)
        
        # Setup complex locator chain
        def locator_side_effect(selector):
            if selector == 'div.metadata-table':
                return mock_tables
            elif selector == '> h3':
                return mock_h3
            elif selector == 'tr':
                return mock_rows
            elif selector == 'td':
                return mock_tds
            return Mock()
        
        mock_page.locator.side_effect = locator_side_effect
        mock_tables.count.return_value = 1
        mock_tables.nth.return_value = mock_table
        mock_table.locator.side_effect = locator_side_effect
        mock_h3.count.return_value = 1
        mock_h3.first.inner_text.return_value = "Topics"
        mock_rows.count.return_value = 1
        mock_rows.nth.return_value = mock_row
        mock_row.locator.return_value = mock_tds
        mock_tds.count.return_value = 2
        mock_tds.nth.side_effect = [
            Mock(inner_text=lambda: "Tags"),
            Mock(inner_text=lambda: "keyword1, keyword2")
        ]
        
        result = extractor._extract_keywords()
        
        self.assertEqual(result, "keyword1, keyword2")
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_extract_keywords_not_found(self, mock_playwright: Mock) -> None:
        """Test _extract_keywords returns None when not found."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        mock_tables = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        extractor = SocrataMetadataExtractor(self.collector)
        
        mock_page.locator.return_value = mock_tables
        mock_tables.count.return_value = 0
        
        result = extractor._extract_keywords()
        
        self.assertIsNone(result)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_extract_all_metadata_success(self, mock_playwright: Mock) -> None:
        """Test extract_all_metadata extracts all metadata and updates result."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        extractor = SocrataMetadataExtractor(self.collector)
        
        # Mock all extraction methods
        with patch.object(extractor, '_extract_title', return_value="Test Title"), \
             patch.object(extractor, '_extract_dataset_metadata', return_value=("1000", "25")), \
             patch.object(extractor, '_extract_description', return_value="<p>Description</p>"), \
             patch.object(extractor, '_extract_keywords', return_value="tag1, tag2"):
            
            result = extractor.extract_all_metadata()
        
        expected = {
            'title': "Test Title",
            'rows': "1000",
            'columns': "25",
            'description': "<p>Description</p>",
            'keywords': "tag1, tag2"
        }
        
        self.assertEqual(result, expected)
        self.assertEqual(self.collector._result.get("title"), expected["title"])
        self.assertEqual(self.collector._result.get("summary"), expected["description"])
        self.assertEqual(self.collector._result.get("keywords"), expected["keywords"])

    @patch("collectors.SocrataCollector.sync_playwright")
    def test_extract_all_metadata_partial(self, mock_playwright: Mock) -> None:
        """Test extract_all_metadata handles partial metadata."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        extractor = SocrataMetadataExtractor(self.collector)
        
        # Mock some extraction methods to return None
        with patch.object(extractor, '_extract_title', return_value="Test Title"), \
             patch.object(extractor, '_extract_dataset_metadata', return_value=(None, None)), \
             patch.object(extractor, '_extract_description', return_value=None), \
             patch.object(extractor, '_extract_keywords', return_value="tag1"):
            
            result = extractor.extract_all_metadata()
        
        expected = {
            'title': "Test Title",
            'rows': None,
            'columns': None,
            'description': None,
            'keywords': "tag1"
        }
        
        self.assertEqual(result, expected)
        self.assertEqual(self.collector._result.get("title"), expected["title"])
        self.assertEqual(self.collector._result.get("summary"), expected["description"])
        self.assertEqual(self.collector._result.get("keywords"), expected["keywords"])
