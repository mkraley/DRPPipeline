"""
Unit tests for datalumos_search.
"""

import os
import unittest
from unittest.mock import patch

from utils.Args import Args
from utils.Logger import Logger
from playwright.sync_api import sync_playwright

from duplicate_checking.datalumos_search import (
    DATALUMOS_SEARCH_BASE,
    _extract_original_distribution_url_from_page,
    _fetch_search_page,
    _parse_num_found,
    _parse_result_ids,
    search_datalumos,
    verify_source_url_in_datalumos,
)


class TestParseNumFound(unittest.TestCase):
    """Test cases for _parse_num_found."""

    def test_parses_num_found(self) -> None:
        """Test _parse_num_found extracts numFound from JSON-like text."""
        text = '{"response":{"docs":[],"numFound":3,"start":0}}'
        self.assertEqual(_parse_num_found(text), 3)

    def test_returns_minus_one_when_missing(self) -> None:
        """Test _parse_num_found returns -1 when numFound absent."""
        self.assertEqual(_parse_num_found("<html><body>unexpected</body></html>"), -1)

    def test_parses_embedded_react_response(self) -> None:
        """Test _parse_num_found works with React-embedded response."""
        text = (
            'ReactDOM.render(React.createElement(SearchPage, {searchResults : '
            '{"response":{"docs":[],"numFound":1,"start":0},'
            '"responseHeader":{}}, searchConfig : {}}), document.getElementById("search"));'
        )
        self.assertEqual(_parse_num_found(text), 1)


class TestFetchSearchPage(unittest.TestCase):
    """Test cases for _fetch_search_page."""

    def setUp(self) -> None:
        import sys
        self._original_argv = sys.argv.copy()
        sys.argv = ["test"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        import sys
        sys.argv = self._original_argv

    def test_returns_none_when_goto_raises(self) -> None:
        """Test _fetch_search_page returns None and logs when page.goto raises."""
        mock_page = unittest.mock.MagicMock()
        mock_page.goto.side_effect = OSError("timeout")

        result = _fetch_search_page(
            "https://www.datalumos.org/datalumos/search/studies?q=foo",
            30_000,
            "https://example.com",
            mock_page,
        )

        self.assertIsNone(result)


class TestParseResultIds(unittest.TestCase):
    """Test cases for _parse_result_ids."""

    def test_parses_ids_from_docs(self) -> None:
        """Test _parse_result_ids extracts IDs from embedded docs."""
        text = '{"response":{"docs":[{"ID":243433,"TITLE":"x"},{"ID":100486}],"numFound":2,"start":0}}'
        self.assertEqual(_parse_result_ids(text), [243433, 100486])

    def test_returns_empty_when_no_ids(self) -> None:
        """Test _parse_result_ids returns empty list when no IDs present."""
        self.assertEqual(_parse_result_ids("<html><body>x</body></html>"), [])


class TestExtractOriginalDistributionUrl(unittest.TestCase):
    """Test cases for _extract_original_distribution_url_from_page (Playwright)."""

    def setUp(self) -> None:
        import sys
        self._original_argv = sys.argv.copy()
        sys.argv = ["test"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        import sys
        sys.argv = self._original_argv

    def _odu_from_html(self, html: str) -> str | None:
        """Load HTML into a Playwright page and extract ODU."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(html)
                return _extract_original_distribution_url_from_page(page)
            finally:
                browser.close()

    def test_extracts_odu_from_dt_dd(self) -> None:
        """Test ODU extracted from dt/dd with adjacent a."""
        html = """
        <dl>
          <dt>Original Distribution URL:</dt>
          <dd><a href="https://example.com">https://example.com/data</a></dd>
        </dl>
        """
        self.assertEqual(self._odu_from_html(html), "https://example.com/data")

    def test_extracts_odu_from_label_and_anchor(self) -> None:
        """Test ODU extracted when label and a share same parent."""
        html = """
        <div><label>Original Distribution URL:</label>
        <a href="https://data.cdc.gov/x/y">https://data.cdc.gov/x/y</a></div>
        """
        self.assertEqual(self._odu_from_html(html), "https://data.cdc.gov/x/y")

    def test_returns_none_when_missing(self) -> None:
        """Test ODU returns None when label or anchor absent."""
        self.assertIsNone(self._odu_from_html("<html><body>foo</body></html>"))


class TestDatalumosSearch(unittest.TestCase):
    """Test cases for search_datalumos."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        import sys
        self._original_argv = sys.argv.copy()
        sys.argv = ["test"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Clean up after each test."""
        import sys
        sys.argv = self._original_argv

    @patch("duplicate_checking.datalumos_search.sync_playwright")
    @patch("duplicate_checking.datalumos_search._fetch_search_page")
    def test_search_datalumos_returns_num_found(
        self,
        mock_fetch: unittest.mock.MagicMock,
        mock_pw: unittest.mock.MagicMock,
    ) -> None:
        """Test search_datalumos parses numFound from fetched page."""
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            unittest.mock.MagicMock()
        )
        mock_fetch.return_value = (
            '{"response":{"docs":[],"numFound":3,"start":0},'
            '"responseHeader":{}}'
        )

        n = search_datalumos("https://data.cdc.gov/x/y/about_data")

        self.assertEqual(n, 3)
        call_args = mock_fetch.call_args
        self.assertTrue(str(call_args[0][0]).startswith(DATALUMOS_SEARCH_BASE))
        self.assertIn("q=https%3A%2F%2Fdata.cdc.gov%2Fx%2Fy%2Fabout_data", call_args[0][0])

    @patch("duplicate_checking.datalumos_search.sync_playwright")
    @patch("duplicate_checking.datalumos_search._fetch_search_page")
    def test_search_datalumos_zero_matches(
        self,
        mock_fetch: unittest.mock.MagicMock,
        mock_pw: unittest.mock.MagicMock,
    ) -> None:
        """Test search_datalumos returns 0 when numFound is 0."""
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            unittest.mock.MagicMock()
        )
        mock_fetch.return_value = '{"response":{"docs":[],"numFound":0,"start":0}}'

        n = search_datalumos("https://example.com/nonexistent")

        self.assertEqual(n, 0)

    @patch("duplicate_checking.datalumos_search.sync_playwright")
    @patch("duplicate_checking.datalumos_search._fetch_search_page")
    def test_search_datalumos_fetch_error_returns_minus_one(
        self,
        mock_fetch: unittest.mock.MagicMock,
        mock_pw: unittest.mock.MagicMock,
    ) -> None:
        """Test search_datalumos returns -1 when fetch fails (e.g. _fetch_search_page returns None)."""
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            unittest.mock.MagicMock()
        )
        mock_fetch.return_value = None

        n = search_datalumos("https://example.com")

        self.assertEqual(n, -1)

    @patch("duplicate_checking.datalumos_search.sync_playwright")
    @patch("duplicate_checking.datalumos_search._fetch_search_page")
    def test_search_datalumos_no_num_found_returns_minus_one(
        self,
        mock_fetch: unittest.mock.MagicMock,
        mock_pw: unittest.mock.MagicMock,
    ) -> None:
        """Test search_datalumos returns -1 when response lacks numFound."""
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            unittest.mock.MagicMock()
        )
        mock_fetch.return_value = "<html><body>unexpected</body></html>"

        n = search_datalumos("https://example.com")

        self.assertEqual(n, -1)

    @patch("duplicate_checking.datalumos_search.sync_playwright")
    @patch("duplicate_checking.datalumos_search._fetch_search_page")
    @patch("duplicate_checking.datalumos_search.Logger")
    def test_search_datalumos_cloudflare_warning(
        self,
        mock_logger: unittest.mock.MagicMock,
        mock_fetch: unittest.mock.MagicMock,
        mock_pw: unittest.mock.MagicMock,
    ) -> None:
        """Test search_datalumos warns when Cloudflare challenge page is detected."""
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            unittest.mock.MagicMock()
        )
        mock_fetch.return_value = '<html><title>Just a moment...</title></html>'

        n = search_datalumos("https://example.com/data")

        self.assertEqual(n, -1)
        mock_logger.warning.assert_called()
        call_args = " ".join(str(c) for c in mock_logger.warning.call_args[0])
        self.assertIn("Cloudflare", call_args)

    @patch("duplicate_checking.datalumos_search.sync_playwright")
    @patch("duplicate_checking.datalumos_search._fetch_search_page")
    @patch("duplicate_checking.datalumos_search.Logger")
    def test_search_datalumos_multi_match_warning(
        self,
        mock_logger: unittest.mock.MagicMock,
        mock_fetch: unittest.mock.MagicMock,
        mock_pw: unittest.mock.MagicMock,
    ) -> None:
        """Test search_datalumos warns when more than one match is returned."""
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            unittest.mock.MagicMock()
        )
        mock_fetch.return_value = '{"response":{"docs":[{},{}],"numFound":2,"start":0}}'

        n = search_datalumos("https://example.com/data")

        self.assertEqual(n, 2)
        mock_logger.warning.assert_called_once()
        call_args = " ".join(str(c) for c in mock_logger.warning.call_args[0])
        self.assertIn("2 matches", call_args)
        self.assertIn("expected at most one", call_args)


class TestVerifySourceUrlInDatalumos(unittest.TestCase):
    """Test cases for verify_source_url_in_datalumos."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        import sys
        self._original_argv = sys.argv.copy()
        sys.argv = ["test"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Clean up after each test."""
        import sys
        sys.argv = self._original_argv

    @patch("duplicate_checking.datalumos_search.sync_playwright")
    def test_verify_returns_true_when_odu_matches(
        self, mock_pw: unittest.mock.MagicMock
    ) -> None:
        """Test verify returns True when a result's ODU matches the search URL."""
        search_html = '{"response":{"docs":[{"ID":99}],"numFound":1,"start":0}}'
        mock_page = unittest.mock.MagicMock()
        mock_page.content.return_value = search_html
        mock_page.evaluate.return_value = "https://example.com/d"
        mock_browser = unittest.mock.MagicMock()
        mock_browser.new_page.return_value = mock_page
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )

        result = verify_source_url_in_datalumos("https://example.com/d")

        self.assertTrue(result)
        self.assertEqual(mock_page.goto.call_count, 2)
        mock_page.evaluate.assert_called_once()

    @patch("duplicate_checking.datalumos_search.sync_playwright")
    @patch("duplicate_checking.datalumos_search.Logger")
    def test_verify_returns_false_and_warns_when_odu_mismatch(
        self, mock_logger: unittest.mock.MagicMock, mock_pw: unittest.mock.MagicMock
    ) -> None:
        """Test verify returns False and logs when ODU does not match search URL."""
        search_html = '{"response":{"docs":[{"ID":99}],"numFound":1,"start":0}}'
        mock_page = unittest.mock.MagicMock()
        mock_page.content.return_value = search_html
        mock_page.evaluate.return_value = "https://other.com"
        mock_browser = unittest.mock.MagicMock()
        mock_browser.new_page.return_value = mock_page
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )

        result = verify_source_url_in_datalumos("https://example.com/d")

        self.assertFalse(result)
        mock_logger.warning.assert_called()
        calls = " ".join(str(c) for c in mock_logger.warning.call_args_list)
        self.assertIn("no matching Original Distribution URL", calls)
        self.assertIn("https://other.com", calls)

    @patch("duplicate_checking.datalumos_search.sync_playwright")
    @patch("duplicate_checking.datalumos_search.Logger")
    def test_verify_warns_when_result_page_goto_fails(
        self, mock_logger: unittest.mock.MagicMock, mock_pw: unittest.mock.MagicMock
    ) -> None:
        """Test verify logs warning and continues when loading a result URL fails."""
        search_html = '{"response":{"docs":[{"ID":99},{"ID":100}],"numFound":2,"start":0}}'
        mock_page = unittest.mock.MagicMock()
        mock_page.content.return_value = search_html
        mock_page.evaluate.return_value = "https://example.com/d"
        mock_page.goto.side_effect = [None, OSError("timeout"), None]
        mock_browser = unittest.mock.MagicMock()
        mock_browser.new_page.return_value = mock_page
        mock_pw.return_value.__enter__.return_value.chromium.launch.return_value = (
            mock_browser
        )

        result = verify_source_url_in_datalumos("https://example.com/d")

        self.assertTrue(result)
        mock_logger.warning.assert_called()
        calls = " ".join(str(c) for c in mock_logger.warning.call_args_list)
        self.assertIn("Failed to load datalumos result page", calls)


# Known CDC URL that exists in datalumos (used by live test).
BRFSS_Vision_Module = (
    "https://data.cdc.gov/Vision-Eye-Health/BRFSS-Vision-Module-Data-Vision-Eye-Health/"
    "pttf-ck53/about_data"
)


def _network_tests_enabled() -> bool:
    """True if DRP_RUN_NETWORK_TESTS is set to 1, true, or yes (case-insensitive)."""
    v = (os.environ.get("DRP_RUN_NETWORK_TESTS") or "").strip().lower()
    return v in ("1", "true", "yes")


@unittest.skipUnless(
    _network_tests_enabled(),
    "Set DRP_RUN_NETWORK_TESTS=1 to run live datalumos tests (no mocks).",
)
class TestDatalumosSearchLive(unittest.TestCase):
    """
    Live integration tests that hit the real datalumos web site.

    Skipped by default. Enable and run with:

        PowerShell:
            $env:DRP_RUN_NETWORK_TESTS = "1"
            python -m unittest duplicate_checking.test_datalumos_search.TestDatalumosSearchLive -v

        CMD:
            set DRP_RUN_NETWORK_TESTS=1
            python -m unittest duplicate_checking.test_datalumos_search.TestDatalumosSearchLive -v
    """

    def setUp(self) -> None:
        import sys
        self._original_argv = sys.argv.copy()
        sys.argv = ["test"]
        Args.initialize()
        Logger.initialize(log_level="INFO")

    def tearDown(self) -> None:
        import sys
        sys.argv = self._original_argv

    def test_verify_cdc_url_exists_in_datalumos(self) -> None:
        """Hit real datalumos; verify known CDC about_data URL is found (headless=False)."""
        result = verify_source_url_in_datalumos(
            BRFSS_Vision_Module,
            headless=False,
            timeout=45.0,
        )
        self.assertTrue(
            result,
            "Expected verify_source_url_in_datalumos to return True for known CDC URL. "
            "Cloudflare may be blocking; try running with a visible browser (headless=False).",
        )
