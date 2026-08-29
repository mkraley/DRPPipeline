"""URL validation helpers shared by Playwright collectors."""

from __future__ import annotations

from utils.Errors import record_error
from utils.Logger import Logger
from utils.url_utils import access_url, is_valid_url


def validate_and_access_url(drpid: int, url: str) -> bool:
    """
    Validate URL syntax and accessibility; record errors on failure.

    Args:
        drpid: Project DRPID for error logging.
        url: Candidate source URL.

    Returns:
        True when the URL is valid and accessible.
    """
    if not is_valid_url(url):
        record_error(drpid, f"Invalid URL: {url}")
        return False

    access_success, status_msg = access_url(url)
    if not access_success:
        record_error(drpid, f"URL access failed: {url} - {status_msg}")
        return False

    Logger.debug("Successfully accessed URL: %s", url)
    return True
