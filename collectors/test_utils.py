"""
Shared test helpers for collectors tests.
"""

from unittest.mock import Mock


def setup_mock_playwright(mock_playwright: Mock) -> tuple:
    """
    Configure mock_playwright so sync_playwright().start().chromium.launch().new_page()
    works when _init_browser() runs.

    Returns:
        Tuple of (mock_page, mock_browser, mock_playwright_instance).
    """
    mock_playwright_instance = Mock()
    mock_browser = Mock()
    mock_page = Mock()
    mock_playwright.return_value.start.return_value = mock_playwright_instance
    mock_playwright_instance.chromium.launch.return_value = mock_browser
    mock_browser.new_page.return_value = mock_page
    return mock_page, mock_browser, mock_playwright_instance
