"""
Unit tests for DataLumosFormFiller.
"""

import unittest
from unittest.mock import MagicMock

from utils.Args import Args
from utils.Logger import Logger
from upload.DataLumosFormFiller import DataLumosFormFiller, _is_empty


class TestDataLumosFormFiller(unittest.TestCase):
    """Test cases for DataLumosFormFiller."""

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize Logger once for all tests."""
        Logger.initialize(log_level="WARNING")

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self.mock_page = MagicMock()
        self.form_filler = DataLumosFormFiller(self.mock_page, timeout=5000)

    def test_init(self) -> None:
        """Test form filler initialization."""
        self.assertEqual(self.form_filler._page, self.mock_page)
        self.assertEqual(self.form_filler._timeout, 5000)

    def test_is_empty_helper(self) -> None:
        """Test _is_empty helper function."""
        self.assertTrue(_is_empty(None))
        self.assertTrue(_is_empty(""))
        self.assertTrue(_is_empty("   "))
        self.assertFalse(_is_empty("x"))
        self.assertFalse(_is_empty("  x  "))

    def test_wait_for_obscuring_elements_no_busy(self) -> None:
        """Test wait_for_obscuring_elements when no busy overlay present."""
        mock_busy = MagicMock()
        mock_busy.count.return_value = 0
        self.mock_page.locator.return_value = mock_busy
        
        self.form_filler.wait_for_obscuring_elements()
        
        mock_busy.count.assert_called_once()

    def test_wait_for_obscuring_elements_with_busy(self) -> None:
        """Test wait_for_obscuring_elements when busy overlay present."""
        mock_busy = MagicMock()
        mock_busy.count.return_value = 1
        mock_first = MagicMock()
        mock_busy.first = mock_first
        self.mock_page.locator.return_value = mock_busy
        
        self.form_filler.wait_for_obscuring_elements()
        
        mock_first.wait_for.assert_called_once_with(state="hidden", timeout=360000)
        self.mock_page.wait_for_timeout.assert_called_with(500)

    def test_fill_title(self) -> None:
        """Test fill_title fills and saves title."""
        mock_title = MagicMock()
        mock_save = MagicMock()
        mock_continue = MagicMock()
        
        def locator_side_effect(selector):
            if "#title" in selector or "title" in selector:
                return mock_title
            if "save-project" in selector:
                return mock_save
            return MagicMock()
        
        self.mock_page.locator.side_effect = locator_side_effect
        self.mock_page.get_by_role.return_value = mock_continue
        
        with unittest.mock.patch.object(self.form_filler, 'wait_for_obscuring_elements'):
            self.form_filler.fill_title("Test Project")
        
        mock_title.fill.assert_called_once_with("Test Project")
        mock_save.click.assert_called_once()
        mock_continue.click.assert_called_once()

    def test_fill_agency_skips_empty(self) -> None:
        """Test fill_agency skips empty values."""
        with unittest.mock.patch.object(self.form_filler, 'wait_for_obscuring_elements'):
            self.form_filler.fill_agency(["", "  ", "valid"])
        
        # Should only process "valid" - add button clicked once
        self.mock_page.locator.assert_called()

    def test_fill_summary_skips_empty(self) -> None:
        """Test fill_summary returns early for empty input."""
        self.form_filler.fill_summary("")
        self.form_filler.fill_summary("   ")
        
        self.mock_page.locator.assert_not_called()

    def test_fill_original_url_skips_empty(self) -> None:
        """Test fill_original_url returns early for empty input."""
        self.form_filler.fill_original_url("")
        self.form_filler.fill_original_url("   ")
        
        self.mock_page.locator.assert_not_called()

    def test_fill_keywords_skips_short(self) -> None:
        """Test fill_keywords skips keywords with 2 or fewer chars."""
        with unittest.mock.patch.object(self.form_filler, 'wait_for_obscuring_elements'):
            # Should not raise - short keywords are skipped
            self.form_filler.fill_keywords(["ab", "a", "valid_keyword"])

    def test_fill_geographic_coverage_skips_empty(self) -> None:
        """Test fill_geographic_coverage returns early for empty input."""
        self.form_filler.fill_geographic_coverage("")
        
        self.mock_page.locator.assert_not_called()

    def test_fill_time_period_skips_empty(self) -> None:
        """Test fill_time_period returns early when both empty."""
        self.form_filler.fill_time_period(None, None)
        self.form_filler.fill_time_period("", "")
        
        self.mock_page.locator.assert_not_called()

    def test_fill_data_types_skips_empty(self) -> None:
        """Test fill_data_types returns early for empty input."""
        self.form_filler.fill_data_types("")
        
        self.mock_page.locator.assert_not_called()

    def test_fill_collection_notes_skips_empty(self) -> None:
        """Test fill_collection_notes returns early when both empty."""
        self.form_filler.fill_collection_notes("", None)
        self.form_filler.fill_collection_notes("", "")
        
        self.mock_page.locator.assert_not_called()


class TestDataLumosUploaderHelpers(unittest.TestCase):
    """Test DataLumosUploader helper methods."""

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize Args and Logger for uploader tests."""
        import sys
        sys.argv = ["test", "upload"]
        Args._initialized = False
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def test_extract_workspace_id_found(self) -> None:
        """Test _extract_workspace_id extracts ID from URL."""
        from upload.DataLumosUploader import DataLumosUploader
        
        uploader = DataLumosUploader("user", "pass")
        url = "https://www.datalumos.org/datalumos/workspace?goToPath=/datalumos/239181"
        result = uploader._extract_workspace_id(url)
        self.assertEqual(result, "239181")

    def test_extract_workspace_id_not_found(self) -> None:
        """Test _extract_workspace_id returns None when no match."""
        from upload.DataLumosUploader import DataLumosUploader
        
        uploader = DataLumosUploader("user", "pass")
        result = uploader._extract_workspace_id("https://example.com/other")
        self.assertIsNone(result)

    def test_parse_keywords(self) -> None:
        """Test _parse_keywords parses comma-separated string."""
        from upload.DataLumosUploader import DataLumosUploader
        
        uploader = DataLumosUploader("user", "pass")
        result = uploader._parse_keywords("key1, key2, 'key3', [key4]")
        self.assertEqual(result, ["key1", "key2", "key3", "key4"])

    def test_parse_keywords_empty(self) -> None:
        """Test _parse_keywords returns empty list for empty input."""
        from upload.DataLumosUploader import DataLumosUploader
        
        uploader = DataLumosUploader("user", "pass")
        result = uploader._parse_keywords("")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
