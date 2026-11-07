"""
Call the deposit API with the page's bearer token, without rendering the workspace.

The token is an inline ``jwtToken`` assignment in the workspace HTML. A later
project reuses the token already on the open page.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from upload.deposit_page_request import HOME_PATH, WORKSPACE_URL
from utils.Logger import Logger

_TOKEN_RE = re.compile(r"""var jwtToken = ['"]([^'"]+)['"]""")
_TOKEN_ON_PAGE_JS = """() => (typeof jwtToken === "string" ? jwtToken : "")"""
_INSTALL_TOKEN_JS = """(token) => { window.jwtToken = token; }"""
_REQUEST_TIMEOUT_MS = 120000
_TOKEN_RENDER_TIMEOUT_MS = 5 * 60 * 1000


def prepare_deposit_token(page: Page, reporter: Any = None) -> str:
    """
    Return a deposit bearer token.

    Uses a token already defined on the page, then the workspace HTML, and
    renders the workspace only when neither source has one.
    """
    token = page_token(page)
    if token:
        Logger.info("Using the deposit token already on the page")
        return token
    token = workspace_html_token(page)
    if token:
        Logger.info("Read the deposit token from workspace HTML")
        return token
    open_workspace_for_token(page, reporter)
    token = page_token(page)
    if not token:
        raise RuntimeError("Deposit token was not available after opening the workspace")
    return token


def page_token(page: Page) -> str:
    """Return ``jwtToken`` when the current page has one."""
    token = page.evaluate(_TOKEN_ON_PAGE_JS)
    return str(token or "")


def workspace_html_token(page: Page) -> str:
    """Read ``jwtToken`` from the workspace HTML and keep it on the page."""
    response = page.request.get(WORKSPACE_URL, timeout=_REQUEST_TIMEOUT_MS)
    if response.status != 200:
        return ""
    return _install_html_token(page, response.text())


def open_workspace_for_token(page: Page, reporter: Any = None) -> None:
    """Render the workspace until ``jwtToken`` exists, then stop the load.

    The document often contains the token before the script runs. When it
    does not, the deposit app is given five minutes to assign ``jwtToken``.
    Deposit calls send that bearer token themselves.
    """
    from upload.DataLumosAuthenticator import wait_for_human_verification

    Logger.info("Opening DataLumos workspace for deposit API calls")
    page.goto(WORKSPACE_URL, wait_until="domcontentloaded", timeout=_REQUEST_TIMEOUT_MS)
    wait_for_human_verification(page, timeout=60000, reporter=reporter)
    if _install_document_token(page):
        _stop_loading(page)
        return
    _wait_for_rendered_token(page)
    _stop_loading(page)


def _install_html_token(page: Page, html: str) -> str:
    """Install ``jwtToken`` from ``html`` and return it, or return an empty string."""
    token = _token_in_html(html)
    if not token:
        return ""
    page.evaluate(_INSTALL_TOKEN_JS, token)
    return token


def _install_document_token(page: Page) -> bool:
    """Install a token already present in the open document."""
    try:
        html = page.content()
    except PlaywrightError:
        return False
    token = _install_html_token(page, html if isinstance(html, str) else "")
    if not token:
        return False
    Logger.info("Read the deposit token from the open workspace document")
    return True


def _wait_for_rendered_token(page: Page) -> None:
    """Wait until the deposit app assigns ``jwtToken``."""
    url = _page_url(page)
    Logger.info("Waiting up to 5 minutes for the deposit token (url=%s)", url)
    try:
        page.wait_for_function(
            "() => typeof jwtToken === 'string' && jwtToken.length > 0",
            timeout=_TOKEN_RENDER_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            f"Deposit token did not appear within 5 minutes (url={_page_url(page)})"
        ) from exc


def _token_in_html(html: str) -> str:
    """Return the ``jwtToken`` assignment in ``html``, or an empty string."""
    match = _TOKEN_RE.search(html or "")
    if match is None:
        return ""
    return match.group(1)


def _stop_loading(page: Page) -> None:
    """Stop the workspace load once the token has been captured."""
    page.evaluate("() => window.stop()")


def _page_url(page: Page) -> str:
    """Return the current page URL, or an empty string when it cannot be read."""
    try:
        return str(page.url or "")
    except PlaywrightError:
        return ""


def deposit_request(
    page: Page,
    token: str,
    method: str,
    url: str,
    data: Optional[dict[str, str]] = None,
    content_type: Optional[str] = None,
    body: Optional[str] = None,
) -> dict[str, Any]:
    """Perform one deposit request with the browser cookie jar and bearer token."""
    headers = {"Authorization": f"Bearer {token}"}
    started = time.perf_counter()
    response = _send(page, method, url, headers, data, content_type, body)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return {"status": response.status, "body": response.text(), "elapsedMs": elapsed_ms}


def project_path(body: Any) -> str:
    """Read ``/datalumos/{id}`` from a createProject response."""
    if not isinstance(body, dict):
        raise RuntimeError(f"createProject returned an unexpected body: {body!r}"[:300])
    new_path = str(body.get("newPath") or "").strip()
    if not new_path and body.get("id"):
        new_path = f"{HOME_PATH}/{body.get('id')}"
    if not new_path.startswith(f"{HOME_PATH}/"):
        raise RuntimeError(f"createProject did not return a project path: {body!r}"[:300])
    return new_path


def parse_body(body_text: str) -> Any:
    """Return JSON when the body parses, otherwise the raw text."""
    if not body_text.strip():
        return None
    try:
        return json.loads(body_text)
    except json.JSONDecodeError:
        return body_text


def _send(
    page: Page,
    method: str,
    url: str,
    headers: dict[str, str],
    data: Optional[dict[str, str]],
    content_type: Optional[str],
    body: Optional[str] = None,
) -> Any:
    """Send one request. Form fields stay in the body, not the query string."""
    method_upper = method.upper()
    if method_upper == "GET":
        return page.request.get(url, headers=headers, timeout=_REQUEST_TIMEOUT_MS)
    if method_upper == "DELETE":
        return page.request.fetch(
            url, method="DELETE", headers=headers, timeout=_REQUEST_TIMEOUT_MS
        )
    if body is not None:
        headers["Content-Type"] = content_type or "application/json"
        return page.request.post(url, headers=headers, data=body, timeout=_REQUEST_TIMEOUT_MS)
    if data is not None:
        return page.request.post(url, headers=headers, form=data, timeout=_REQUEST_TIMEOUT_MS)
    if content_type:
        headers["Content-Type"] = content_type
    return page.request.fetch(
        url, method="POST", headers=headers, timeout=_REQUEST_TIMEOUT_MS
    )
