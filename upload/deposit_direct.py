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

from playwright.sync_api import Page

from upload.deposit_page_request import HOME_PATH, WORKSPACE_URL
from utils.Logger import Logger

_TOKEN_RE = re.compile(r"""var jwtToken = ['"]([^'"]+)['"]""")
_TOKEN_ON_PAGE_JS = """() => (typeof jwtToken === "string" ? jwtToken : "")"""
_INSTALL_TOKEN_JS = """(token) => { window.jwtToken = token; }"""
_REQUEST_TIMEOUT_MS = 120000


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
    match = _TOKEN_RE.search(response.text())
    if not match:
        return ""
    token = match.group(1)
    page.evaluate(_INSTALL_TOKEN_JS, token)
    return token


def open_workspace_for_token(page: Page, reporter: Any = None) -> None:
    """Render the workspace until its token and jQuery exist, then stop the load."""
    from upload.DataLumosAuthenticator import wait_for_human_verification

    Logger.info("Opening DataLumos workspace for deposit API calls")
    page.goto(WORKSPACE_URL, wait_until="domcontentloaded", timeout=_REQUEST_TIMEOUT_MS)
    wait_for_human_verification(page, timeout=60000, reporter=reporter)
    page.wait_for_function(
        "() => typeof jwtToken === 'string' && jwtToken.length > 0 && "
        "typeof $ !== 'undefined' && typeof $.ajax === 'function'",
        timeout=_REQUEST_TIMEOUT_MS,
    )
    page.evaluate("() => window.stop()")


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
    if method.upper() == "GET":
        return page.request.get(url, headers=headers, timeout=_REQUEST_TIMEOUT_MS)
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
