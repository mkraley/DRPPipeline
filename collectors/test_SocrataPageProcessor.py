"""
Unit tests for SocrataPageProcessor.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from utils.Args import Args
from utils.Logger import Logger

from collectors.SocrataCollector import SocrataCollector
from collectors.SocrataPageProcessor import SocrataPageProcessor
from collectors.test_utils import setup_mock_playwright


class TestSocrataPageProcessor(unittest.TestCase):
    """Test cases for SocrataPageProcessor class."""
    
    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test"]
        
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        
        self.temp_dir = Path(tempfile.mkdtemp())
        with patch.object(Args, 'base_output_dir', self.temp_dir):
            self.collector = SocrataCollector(headless=True)
            self.collector._result = {
                'status': None,
                'pdf_path': None,
                'dataset_path': None,
                'metadata': {},
                'file_extensions': [],
                'dataset_size': None
            }
            self.processor = SocrataPageProcessor(self.collector)
    
    def tearDown(self) -> None:
        """Clean up after each test."""
        sys.argv = self._original_argv
        self.collector._cleanup_browser()
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)
    
    def test_init(self) -> None:
        """Test SocrataPageProcessor initialization."""
        with patch.object(Args, 'base_output_dir', self.temp_dir):
            collector = SocrataCollector(headless=True)
            processor = SocrataPageProcessor(collector)
            self.assertEqual(processor._collector, collector)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_get_total_rows_success(self, mock_playwright: Mock) -> None:
        """Test _get_total_rows extracts total rows from paginator."""
        mock_page, _, _ = setup_mock_playwright(mock_playwright)

        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)

        mock_page.evaluate.return_value = 125
        
        result = processor._get_total_rows()
        
        self.assertEqual(result, 125)
        mock_page.evaluate.assert_called_once()
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_get_total_rows_not_found(self, mock_playwright: Mock) -> None:
        """Test _get_total_rows returns None when paginator not found."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        # Mock evaluate to return None
        mock_page.evaluate.return_value = None
        
        result = processor._get_total_rows()
        
        self.assertIsNone(result)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_get_total_rows_exception(self, mock_playwright: Mock) -> None:
        """Test _get_total_rows handles exceptions."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        # Mock evaluate to raise exception
        mock_page.evaluate.side_effect = Exception("Error")
        
        result = processor._get_total_rows()
        
        self.assertIsNone(result)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_show_all_rows_success(self, mock_playwright: Mock) -> None:
        """Test _show_all_rows successfully sets pagination."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        # Mock evaluate to return success
        mock_page.evaluate.return_value = {'success': True}
        mock_page.wait_for_timeout.return_value = None
        
        result = processor._show_all_rows(150)
        
        self.assertTrue(result)
        self.assertEqual(mock_page.evaluate.call_count, 1)
        mock_page.wait_for_timeout.assert_called_once_with(2000)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_show_all_rows_fallback(self, mock_playwright: Mock) -> None:
        """Test _show_all_rows falls back to 100 when initial attempt fails."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        # Mock evaluate: first call fails, second (fallback) succeeds
        mock_page.evaluate.side_effect = [
            {'success': False},  # First attempt fails
            {'success': True}    # Fallback succeeds
        ]
        mock_page.wait_for_timeout.return_value = None
        
        result = processor._show_all_rows(150)
        
        self.assertTrue(result)
        self.assertEqual(mock_page.evaluate.call_count, 2)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_show_all_rows_small_total(self, mock_playwright: Mock) -> None:
        """Test _show_all_rows uses 100 when total_rows is less than 100."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        mock_page.evaluate.return_value = {'success': True}
        mock_page.wait_for_timeout.return_value = None
        
        result = processor._show_all_rows(50)
        
        self.assertTrue(result)
        # Should use 100, not 50
        call_args = mock_page.evaluate.call_args[0][0]
        self.assertIn('targetSize = 100', call_args)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_expand_read_more_links_success(self, mock_playwright: Mock) -> None:
        """Test _expand_read_more_links successfully clicks buttons."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        mock_locator = Mock()
        mock_buttons = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        # Setup locator chain
        mock_page.locator.return_value = mock_buttons
        mock_buttons.count.return_value = 3
        mock_buttons.nth.return_value = mock_buttons
        mock_buttons.click.return_value = None
        mock_page.wait_for_timeout.return_value = None
        mock_page.evaluate.return_value = None
        
        result = processor._expand_read_more_links()
        
        self.assertEqual(result, 3)
        self.assertEqual(mock_buttons.click.call_count, 3)
        mock_page.wait_for_timeout.assert_called_once_with(1500)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_expand_read_more_links_no_buttons(self, mock_playwright: Mock) -> None:
        """Test _expand_read_more_links when no buttons found."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        mock_buttons = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        mock_page.locator.return_value = mock_buttons
        mock_buttons.count.return_value = 0
        
        result = processor._expand_read_more_links()
        
        self.assertEqual(result, 0)
        mock_buttons.click.assert_not_called()
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_hide_collapse_buttons(self, mock_playwright: Mock) -> None:
        """Test _hide_collapse_buttons hides buttons."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        mock_page.evaluate.return_value = None
        
        # Should not raise exception
        processor._hide_collapse_buttons()
        
        mock_page.evaluate.assert_called_once()
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_generate_pdf_success(self, mock_playwright: Mock) -> None:
        """Test _generate_pdf successfully generates PDF."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        pdf_path = self.temp_dir / "test.pdf"
        mock_page.pdf.return_value = None
        
        result = processor._generate_pdf(pdf_path)
        
        self.assertTrue(result)
        mock_page.pdf.assert_called_once_with(
            path=str(pdf_path),
            format='A4',
            print_background=True
        )
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_generate_pdf_failure(self, mock_playwright: Mock) -> None:
        """Test _generate_pdf handles PDF generation failure."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        pdf_path = self.temp_dir / "test.pdf"
        mock_page.pdf.side_effect = Exception("PDF generation failed")
        
        result = processor._generate_pdf(pdf_path)
        
        self.assertFalse(result)
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_generate_pdf_full_flow(self, mock_playwright: Mock) -> None:
        """Test generate_pdf() full flow with all steps."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        mock_buttons = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        pdf_path = self.temp_dir / "test.pdf"
        
        # Mock all method calls
        mock_page.evaluate.side_effect = [
            125,  # _get_total_rows
            {'success': True},  # _show_all_rows
            None  # _hide_collapse_buttons
        ]
        mock_page.locator.return_value = mock_buttons
        mock_buttons.count.return_value = 2
        mock_buttons.nth.return_value = mock_buttons
        mock_buttons.click.return_value = None
        mock_page.wait_for_timeout.return_value = None
        mock_page.pdf.return_value = None
        
        result = processor.generate_pdf(pdf_path)
        
        self.assertTrue(result)
        self.assertEqual(self.collector._result['pdf_path'], str(pdf_path))
        self.assertIn('PDF', self.collector._result['file_extensions'])
        self.assertIn('PDF generated', self.collector._result['status'])
    
    @patch('collectors.SocrataCollector.sync_playwright')
    def test_generate_pdf_updates_result_on_failure(self, mock_playwright: Mock) -> None:
        """Test generate_pdf() updates result on failure."""
        mock_playwright_instance = Mock()
        mock_browser = Mock()
        mock_page = Mock()
        
        mock_playwright.return_value.start.return_value = mock_playwright_instance
        mock_playwright_instance.chromium.launch.return_value = mock_browser
        mock_browser.new_page.return_value = mock_page
        
        self.collector._init_browser()
        processor = SocrataPageProcessor(self.collector)
        
        pdf_path = self.temp_dir / "test.pdf"
        
        # evaluate: 1) _get_total_rows -> int; 2) _show_all_rows -> dict
        mock_page.evaluate.side_effect = [125, {'success': True}]
        mock_page.locator.return_value = Mock(count=lambda: 0)
        mock_page.pdf.side_effect = Exception("PDF failed")
        
        result = processor.generate_pdf(pdf_path)
        
        self.assertFalse(result)
        self.assertIn('PDF generation failed', self.collector._result['status'])
