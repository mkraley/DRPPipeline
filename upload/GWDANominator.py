"""
GWDA (U.S. Government Web & Data Archive) URL nominator.

Nominates source URLs to the GWDA nomination form using Playwright.
Reads config (your_name, institution, email) from Args.
"""

from typing import Optional, Tuple

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.Args import Args
from utils.Logger import Logger


NOMINATION_URL = "https://digital2.library.unt.edu/nomination/GWDA-US-2025/add/"


class GWDANominator:
    """
    Nominates URLs to the U.S. Government Web & Data Archive (GWDA).

    Fills the GWDA nomination form: URL, Your Name, Institution, Email,
    then submits. Config values come from Args.
    """

    def __init__(self, page: Page, timeout: int = 30000) -> None:
        """
        Initialize the GWDA nominator.

        Args:
            page: Playwright Page object
            timeout: Timeout in milliseconds for form interactions
        """
        self._page = page
        self._timeout = timeout

    def nominate(self, source_url: str) -> Tuple[bool, Optional[str]]:
        """
        Nominate a URL to GWDA.

        Reads your_name, institution, and email from Args (gwda_email
        falls back to datalumos_username if not set).

        Args:
            source_url: The URL to nominate

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        if not source_url or not source_url.strip():
            return False, "Source URL is empty, cannot nominate"

        email = Args.gwda_email
        if not email or not str(email).strip():
            return False, (
                "GWDA nomination requires email "
                "(set gwda_email or datalumos_username in config)"
            )

        your_name = Args.gwda_your_name
        institution = Args.gwda_institution

        Logger.info(f"Nominating URL to GWDA: {source_url}")

        try:
            self._page.goto(NOMINATION_URL, wait_until="domcontentloaded")
            self._page.wait_for_load_state("networkidle", timeout=self._timeout)
            self._page.wait_for_timeout(2000)

            self._fill_field("#url-value", source_url)
            self._fill_field("#your-name-value", your_name)
            self._fill_field("#institution-value", institution)
            self._fill_field("#email-value", str(email))

            submit_btn = self._page.locator(
                "input[type='submit'][value='submit']"
            )
            submit_btn.click()
            self._page.wait_for_timeout(2000)

            Logger.info("Successfully nominated URL to GWDA")
            return True, None

        except PlaywrightTimeoutError as e:
            error_msg = f"GWDA nomination timeout: {e}"
            Logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error nominating URL to GWDA: {e}"
            Logger.error(error_msg)
            return False, error_msg

    def _fill_field(self, selector: str, value: str) -> None:
        """Fill a form field and wait briefly."""
        self._page.locator(selector).fill(value)
        self._page.wait_for_timeout(500)
