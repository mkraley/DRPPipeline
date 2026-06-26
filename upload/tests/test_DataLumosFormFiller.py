"""
Unit tests for DataLumosFormFiller.
"""

import re
import unittest
from unittest.mock import MagicMock

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.Args import Args
from utils.Logger import Logger
from upload.DataLumosFormFiller import (
    DataLumosFormFiller,
    _is_empty,
    truncate_title_for_datalumos,
)


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

    def test_truncate_title_for_datalumos_unchanged_when_short(self) -> None:
        title = "Short USFS dataset title"
        self.assertEqual(truncate_title_for_datalumos(title), title)

    def test_truncate_title_for_datalumos_normalizes_whitespace(self) -> None:
        title = "  Fuel   map   2020  "
        self.assertEqual(truncate_title_for_datalumos(title), "Fuel map 2020")

    def test_truncate_title_for_datalumos_breaks_at_word_boundary(self) -> None:
        words = ["word"] * 60
        title = " ".join(words)
        truncated = truncate_title_for_datalumos(title)
        self.assertLessEqual(len(truncated), 250)
        self.assertTrue(truncated.endswith("…"))
        self.assertNotIn("wordword", truncated)

    def test_truncate_title_for_datalumos_hard_cut_for_long_token(self) -> None:
        title = "x" * 300
        truncated = truncate_title_for_datalumos(title)
        self.assertEqual(len(truncated), 250)
        self.assertTrue(truncated.endswith("…"))

    def test_fill_title_truncates_long_title(self) -> None:
        """Test fill_title truncates titles over the DataLumos limit."""
        long_title = "dataset " * 80
        mock_title = MagicMock()
        mock_save_apply = MagicMock()
        mock_continue = MagicMock()

        def locator_side_effect(selector):
            if "#title" in selector:
                return mock_title
            return MagicMock()

        def get_by_role_side_effect(role, name=None):
            if role == "button" and isinstance(name, re.Pattern):
                return mock_save_apply
            if role == "button":
                return mock_continue
            return MagicMock()

        self.mock_page.locator.side_effect = locator_side_effect
        self.mock_page.get_by_role.side_effect = get_by_role_side_effect

        with unittest.mock.patch.object(self.form_filler, "wait_for_obscuring_elements"):
            self.form_filler.fill_title(long_title)

        filled = mock_title.fill.call_args[0][0]
        self.assertLessEqual(len(filled), 250)
        self.assertNotEqual(filled, long_title)

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
        """Test fill_title fills title, Save & Apply, then Continue To Project Workspace."""
        mock_title = MagicMock()
        mock_save_apply = MagicMock()
        mock_continue = MagicMock()

        def locator_side_effect(selector):
            if "#title" in selector:
                return mock_title
            return MagicMock()

        def get_by_role_side_effect(role, name=None):
            if role == "button" and isinstance(name, re.Pattern):
                return mock_save_apply
            if role == "button":
                return mock_continue
            return MagicMock()

        self.mock_page.locator.side_effect = locator_side_effect
        self.mock_page.get_by_role.side_effect = get_by_role_side_effect

        with unittest.mock.patch.object(self.form_filler, "wait_for_obscuring_elements"):
            self.form_filler.fill_title("Test Project")

        mock_title.fill.assert_called_once_with("Test Project")
        mock_save_apply.click.assert_called_once()
        mock_continue.click.assert_called_once()

    def test_fill_agency_skips_empty(self) -> None:
        """Test fill_agency skips empty values."""
        with unittest.mock.patch.object(self.form_filler, 'wait_for_obscuring_elements'):
            self.form_filler.fill_agency(["", "  ", "valid"])
        
        self.mock_page.locator.assert_called()

    def test_fill_summary_skips_empty(self) -> None:
        """Test fill_summary returns early for empty input."""
        self.form_filler.fill_summary("")
        self.form_filler.fill_summary("   ")

        self.mock_page.locator.assert_not_called()

    def test_fill_summary_normalizes_html_before_wysiwyg(self) -> None:
        """Test fill_summary structures HTML for wysihtml5 before editor fill."""
        raw = '<p dir="ltr">Hello <a href="https://example.com">link</a></p><p>Second.</p>'
        with unittest.mock.patch.object(self.form_filler, "_fill_wysiwyg") as mock_fill:
            self.form_filler.fill_summary(raw)

        mock_fill.assert_called_once()
        html_arg = mock_fill.call_args[0][1]
        self.assertNotIn("dir=", html_arg)
        self.assertIn('href="https://example.com"', html_arg)
        self.assertIn("Hello", html_arg)
        self.assertIn("<br><br>", html_arg)
        self.assertIn("Second.", html_arg)

    def test_fill_original_url_skips_empty(self) -> None:
        """Test fill_original_url returns early for empty input."""
        self.form_filler.fill_original_url("")
        self.form_filler.fill_original_url("   ")
        
        self.mock_page.locator.assert_not_called()

    def test_fill_keywords_skips_short(self) -> None:
        """Test fill_keywords skips keywords with 2 or fewer chars."""
        with unittest.mock.patch.object(self.form_filler, 'wait_for_obscuring_elements'):
            self.form_filler.fill_keywords(["ab", "a", "valid_keyword"])

    def test_fill_geographic_coverage_skips_empty(self) -> None:
        """Test fill_geographic_coverage returns early for empty input."""
        self.form_filler.fill_geographic_coverage("")

        self.mock_page.locator.assert_not_called()

    def test_expand_all_sections_skips_missing_toggle(self) -> None:
        """Test expand_all_sections is non-fatal when #expand-init is absent."""
        mock_btn = MagicMock()
        mock_btn.click.side_effect = PlaywrightTimeoutError("missing")
        self.mock_page.locator.return_value = mock_btn

        with unittest.mock.patch.object(self.form_filler, "wait_for_obscuring_elements"):
            self.form_filler.expand_all_sections()

    def test_geographic_coverage_block_uses_label_and_add_value(self) -> None:
        """Geographic add-value is found from the label span and title attribute."""
        mock_label = MagicMock()
        mock_block = MagicMock()
        mock_add = MagicMock()

        mock_label.locator.return_value = mock_block
        mock_block.get_by_title.return_value = mock_add

        with unittest.mock.patch.object(self.form_filler, "wait_for_obscuring_elements"):
            self.mock_page.locator.return_value.filter.return_value.first = mock_label
            self.form_filler._click_geographic_add_value()

        mock_label.locator.assert_called_once_with("xpath=./parent::*/parent::*")
        mock_block.get_by_title.assert_called_once()
        mock_add.click.assert_called_once()

    def test_fill_geographic_coverage_uses_add_value_for_terms(self) -> None:
        """Test fill_geographic_coverage adds each term via add-value flow."""
        with unittest.mock.patch.object(self.form_filler, "wait_for_obscuring_elements"), \
             unittest.mock.patch.object(
                 self.form_filler, "_add_geographic_term"
             ) as mock_add:
            self.form_filler.fill_geographic_coverage("Oregon; United States")

        self.assertEqual(mock_add.call_count, 2)
        mock_add.assert_any_call("Oregon")
        mock_add.assert_any_call("United States")

    def test_fill_time_period_skips_empty(self) -> None:
        """Test fill_time_period returns early when both empty."""
        self.form_filler.fill_time_period(None, None)
        self.form_filler.fill_time_period("", "")
        
        self.mock_page.locator.assert_not_called()

    def test_fill_data_types_skips_empty(self) -> None:
        """Test fill_data_types returns early for empty input."""
        self.form_filler.fill_data_types("")
        
        self.mock_page.locator.assert_not_called()

    def test_fill_data_types_selects_multiple(self) -> None:
        """Test fill_data_types selects each semicolon-delimited checklist option."""
        mock_edit = MagicMock()
        mock_save = MagicMock()
        mock_labels = [MagicMock(), MagicMock()]

        def locator_side_effect(selector: str) -> MagicMock:
            if "#disco_kindOfData_0" in selector:
                return mock_edit
            if "editable-submit" in selector:
                return mock_save
            if "Observational data" in selector:
                return mock_labels[0]
            if "Geographic information system (GIS) data" in selector:
                return mock_labels[1]
            return MagicMock()

        self.mock_page.locator.side_effect = locator_side_effect

        with unittest.mock.patch.object(self.form_filler, "wait_for_obscuring_elements"):
            self.form_filler.fill_data_types(
                "Observational data; Geographic information system (GIS) data"
            )

        mock_edit.click.assert_called_once()
        mock_labels[0].click.assert_called_once()
        mock_labels[1].click.assert_called_once()
        mock_save.click.assert_called_once()

    def test_fill_collection_notes_skips_empty(self) -> None:
        """Test fill_collection_notes returns early when both empty."""
        self.form_filler.fill_collection_notes("", None)
        self.form_filler.fill_collection_notes("", "")
        
        self.mock_page.locator.assert_not_called()

    def test_fill_keywords_persists_warning_via_reporter(self) -> None:
        reporter = MagicMock()
        form_filler = DataLumosFormFiller(self.mock_page, timeout=5000, reporter=reporter)
        mock_search = MagicMock()
        mock_search.click.side_effect = PlaywrightTimeoutError("timeout")
        self.mock_page.locator.return_value = mock_search

        with unittest.mock.patch.object(form_filler, "wait_for_obscuring_elements"):
            form_filler.fill_keywords(["Oregon"])

        reporter.warn.assert_called_once()
        self.assertIn("Oregon", reporter.warn.call_args[0][0])


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
        
        uploader = DataLumosUploader()
        url = "https://www.datalumos.org/datalumos/workspace?goToPath=/datalumos/239181"
        result = uploader._extract_workspace_id(url)
        self.assertEqual(result, "239181")

    def test_extract_workspace_id_not_found(self) -> None:
        """Test _extract_workspace_id returns None when no match."""
        from upload.DataLumosUploader import DataLumosUploader
        
        uploader = DataLumosUploader()
        result = uploader._extract_workspace_id("https://example.com/other")
        self.assertIsNone(result)

    def test_parse_keywords(self) -> None:
        """Test _parse_keywords parses comma-separated string."""
        from upload.DataLumosUploader import DataLumosUploader
        
        uploader = DataLumosUploader()
        result = uploader._parse_keywords("key1, key2, 'key3', [key4]")
        self.assertEqual(result, ["key1", "key2", "key3", "key4"])

    def test_parse_keywords_semicolon_or_comma(self) -> None:
        """Test _parse_keywords splits on semicolons or commas."""
        from upload.DataLumosUploader import DataLumosUploader

        uploader = DataLumosUploader()
        self.assertEqual(uploader._parse_keywords("a; b; c"), ["a", "b", "c"])
        self.assertEqual(uploader._parse_keywords("a, b; c"), ["a", "b", "c"])
        self.assertEqual(
            uploader._parse_keywords(
                "inlandWaters; Ecology, Ecosystems, & Environment; organic matter"
            ),
            [
                "inlandWaters",
                "Ecology",
                "Ecosystems",
                "Environment",
                "organic matter",
            ],
        )

    def test_parse_keywords_empty(self) -> None:
        """Test _parse_keywords returns empty list for empty input."""
        from upload.DataLumosUploader import DataLumosUploader
        
        uploader = DataLumosUploader()
        result = uploader._parse_keywords("")
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
