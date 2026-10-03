"""
GWDA (U.S. Government Web & Data Archive) URL nominator.

Nominates source URLs to the GWDA nomination form using Playwright.
Reads config (your_name, institution, email) from Args.
Skips URLs that are already on the public GWDA nomination list.
"""

from typing import Optional, Tuple
from urllib.parse import urlparse

import requests
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.Args import Args
from utils.Logger import Logger


NOMINATION_URL = "https://digital2.library.unt.edu/nomination/GWDA-US-2025/add/"
URL_REPORT = "https://digital2.library.unt.edu/nomination/GWDA-US-2025/reports/urls/"
_URL_REPORT_TIMEOUT_SEC = 60


class GWDANominator:
    """
    Nominates URLs to the U.S. Government Web & Data Archive (GWDA).

    Fills the GWDA nomination form: URL, Your Name, Institution, Email,
    then submits. Config values come from Args. URLs already listed in the
    public GWDA URL report are not submitted again.
    """

    _nominated_url_keys: set[str] | None = None
    _url_list_checked: bool = False

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

        Reads your_name, institution, and email from Args. ``gwda_email``
        must be set in config. A URL already on the GWDA list is treated as
        success and is not submitted again.

        Args:
            source_url: The URL to nominate

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        if not source_url or not source_url.strip():
            return False, "Source URL is empty, cannot nominate"
        if self._already_nominated(source_url):
            Logger.info(f"GWDA already has this URL; skipping nomination: {source_url}")
            return True, None
        return self._submit_nomination(source_url.strip())

    def _already_nominated(self, source_url: str) -> bool:
        """
        Return True when the URL is already on the GWDA nomination list.

        Args:
            source_url: URL about to be nominated.

        Returns:
            True when a matching URL is listed. False when it is absent or the
            list could not be loaded.
        """
        listed = self._nominated_url_keys_or_none()
        if listed is None:
            return False
        return bool(_lookup_keys(source_url).intersection(listed))

    def _nominated_url_keys_or_none(self) -> set[str] | None:
        """
        Return cached GWDA URL keys, loading the public report once.

        Returns:
            Comparison keys, or None when the report could not be loaded.
        """
        if GWDANominator._url_list_checked:
            return GWDANominator._nominated_url_keys
        GWDANominator._url_list_checked = True
        GWDANominator._nominated_url_keys = _download_nominated_url_keys()
        return GWDANominator._nominated_url_keys

    def _submit_nomination(self, source_url: str) -> Tuple[bool, Optional[str]]:
        """
        Fill and submit the GWDA nomination form.

        Args:
            source_url: URL to nominate.

        Returns:
            Tuple of (success, error message).
        """
        email = Args.gwda_email
        if not email or not str(email).strip():
            return False, (
                "GWDA nomination requires email (set gwda_email in config)"
            )

        Logger.info(f"Nominating URL to GWDA: {source_url}")
        try:
            self._page.goto(NOMINATION_URL, wait_until="domcontentloaded")
            self._page.wait_for_load_state("networkidle", timeout=self._timeout)
            self._page.wait_for_timeout(2000)
            self._fill_field("#url-value", source_url)
            self._fill_field("#your-name-value", Args.gwda_your_name)
            self._fill_field("#institution-value", Args.gwda_institution)
            self._fill_field("#email-value", str(email))
            self._page.locator("input[type='submit'][value='submit']").click()
            self._page.wait_for_timeout(2000)
            Logger.info("Successfully nominated URL to GWDA")
            return True, None
        except PlaywrightTimeoutError as exc:
            return False, f"GWDA nomination timeout: {exc}"
        except Exception as exc:
            return False, f"Error nominating URL to GWDA: {exc}"

    def _fill_field(self, selector: str, value: str) -> None:
        """Fill a form field and wait briefly."""
        self._page.locator(selector).fill(value)
        self._page.wait_for_timeout(500)


def _lookup_keys(url: str) -> set[str]:
    """
    Return http and https comparison keys for one URL.

    Args:
        url: URL to match against the GWDA list.

    Returns:
        Keys that should count as the same nomination.
    """
    key = _url_key(url)
    if key.startswith("https://"):
        alternate = "http://" + key[len("https://"):]
    elif key.startswith("http://"):
        alternate = "https://" + key[len("http://"):]
    else:
        alternate = key
    return {key, alternate}


def _url_key(url: str) -> str:
    """
    Normalize a URL for GWDA list comparison.

    Args:
        url: Raw URL from the project or the GWDA report.

    Returns:
        Scheme and host lowercased, fragment removed, trailing slash stripped.
    """
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}{query}"


def _download_nominated_url_keys() -> set[str] | None:
    """
    Download the public GWDA URL report.

    Returns:
        Comparison keys, or None when the report cannot be read.
    """
    try:
        response = requests.get(URL_REPORT, timeout=_URL_REPORT_TIMEOUT_SEC)
        response.raise_for_status()
    except requests.RequestException as exc:
        Logger.warning(
            "Could not load the GWDA URL list (%s); nominating anyway",
            exc,
        )
        return None
    return {
        _url_key(line)
        for line in response.text.splitlines()
        if line.strip() and not line.startswith("#")
    }
