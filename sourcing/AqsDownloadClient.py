"""Fetch the EPA AirData pre-generated download page."""

from __future__ import annotations

from collections.abc import Callable

import requests

from sourcing.AqsSeries import DOWNLOAD_PAGE_URL
from utils.url_utils import requests_verify

DEFAULT_TIMEOUT_SEC = 60
_USER_AGENT = "DRPPipeline"


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
