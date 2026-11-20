"""Fetch the EPA AirData pre-generated download page."""

from __future__ import annotations

from collections.abc import Callable

import requests

from sourcing.AqsSeries import DOWNLOAD_PAGE_URL
from utils.url_utils import requests_verify

DEFAULT_TIMEOUT_SEC = 60
_USER_AGENT = "DRPPipeline"
AIRDATA_FILE_ROOT = "https://aqs.epa.gov/aqsweb/airdata/"


class AqsDownloadClient:
    """HTTP client for the AirData pre-generated files page."""

    def __init__(
        self,
        *,
        getter: Callable[..., requests.Response] | None = None,
        page_url: str = DOWNLOAD_PAGE_URL,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        """
        Initialize the client.

        Args:
            getter: ``requests.get`` replacement for tests.
            page_url: Download page URL.
            timeout_sec: HTTP timeout in seconds.
        """
        self._get = getter or requests.get
        self._page_url = page_url
        self._timeout_sec = timeout_sec

    def fetch_html(self) -> str:
        """
        Download the pre-generated files page.

        Returns:
            HTML body of the download page.

        Raises:
            RuntimeError: When the request fails or the status is not 200.
        """
        response = self._request()
        self._require_ok(response)
        return response.text

    def _request(self) -> requests.Response:
        """Perform the page GET."""
        try:
            return self._get(
                self._page_url,
                headers={"User-Agent": _USER_AGENT},
                timeout=self._timeout_sec,
                verify=requests_verify(),
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"AirData download page request failed: {exc}") from exc

    def _require_ok(self, response: requests.Response) -> None:
        """Raise when the download page response is not successful."""
        if response.status_code != 200:
            raise RuntimeError(
                f"AirData download page returned HTTP {response.status_code}"
            )

    def content_length(self, url: str) -> int | None:
        """
        Return the Content-Length for one AirData file.

        Args:
            url: Absolute file URL.

        Returns:
            Byte length, or None when the header is missing or the request fails.
        """
        try:
            response = self._get(
                url,
                headers={"User-Agent": _USER_AGENT},
                timeout=self._timeout_sec,
                verify=requests_verify(),
                stream=True,
            )
        except requests.RequestException:
            return None
        try:
            if response.status_code != 200:
                return None
            return _content_length(response.headers.get("Content-Length"))
        finally:
            response.close()


def file_url(filename: str) -> str:
    """
    Return the absolute URL for a file named on the download page.

    Args:
        filename: Zip, HTML, CSV, or PDF name.
    """
    return f"{AIRDATA_FILE_ROOT}{filename}"


def _content_length(raw: str | None) -> int | None:
    """Parse a Content-Length header."""
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
