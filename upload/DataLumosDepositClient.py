"""
Call the ICPSR deposit API from an already authenticated DataLumos page.

Requests go through the page's jQuery so the in-page session can attach its
bearer token. The token is not returned to Python. ``global: false`` keeps
these calls from raising the workspace ``#busy`` overlay.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Page

from upload.DepositAttribute import DepositAttribute, flatten_attributes
from upload.deposit_field_match import suggestion_texts
from upload.deposit_page_request import (
    AJAX_JS,
    DEPOSIT_SERVER,
    HOME_PATH,
    WORKSPACE_URL,
    append_deposit_log,
    encode_query,
    redact_secrets,
)
from utils.Logger import Logger


class DataLumosDepositClient:
    """Deposit API calls for one authenticated Playwright page."""

    def __init__(self, page: Page, log_path: Path | None = None) -> None:
        """
        Args:
            page: Playwright page that will be logged into DataLumos.
            log_path: Optional JSONL file for redacted request summaries.
        """
        self._page = page
        self._log_path = log_path
        self._ready = False

    def ensure_deposit_page(self) -> None:
        """Open the workspace far enough to load jQuery and the page token."""
        if self._ready:
            return
        from upload.DataLumosAuthenticator import wait_for_human_verification

        Logger.info("Opening DataLumos workspace for deposit API calls")
        self._page.goto(WORKSPACE_URL, wait_until="domcontentloaded", timeout=120000)
        wait_for_human_verification(self._page, timeout=60000)
        self._page.wait_for_function(
            "() => typeof jwtToken === 'string' && jwtToken.length > 0 && "
            "typeof $ !== 'undefined' && typeof $.ajax === 'function'",
            timeout=120000,
        )
        self._page.evaluate("() => window.stop()")
        self._ready = True

    def create_project(self, title: str) -> str:
        """
        Create a project and return its ``/datalumos/{id}`` path.

        Args:
            title: Display name, already truncated for DataLumos.
        """
        payload = json.dumps(
            {
                "resourceUri": HOME_PATH,
                "tenant": "datalumos",
                "displayName": title,
                "archive": "datalumos",
            },
            separators=(",", ":"),
        )
        url = (
            f"{DEPOSIT_SERVER}/createProject?newProject={encode_query(payload)}"
            "&prjType=general"
        )
        return _project_path(self._call("POST", url, content_type="application/json"))

    def get_attributes(self, path: str) -> list[DepositAttribute]:
        """Load project attributes once. The caller decides whether to refresh."""
        url = (
            f"{DEPOSIT_SERVER}/getAttributes?pathUrl={encode_query(path)}"
            "&tenant=datalumos&level=project"
        )
        attrs = flatten_attributes(self._call("GET", url))
        if not attrs:
            raise RuntimeError("getAttributes returned no resource properties")
        return attrs

    def post_property(self, path: str, name: str, value: str, label: str) -> None:
        """POST one attribute value. The value travels in the form body, not the query."""
        url = f"{DEPOSIT_SERVER}/postProperty?label={encode_query(label)}"
        self._call("POST", url, data={"name": name, "pk": path, "value": value})

    def add_organization(self, path: str, name: str, org_name: str) -> None:
        """Add one agency or office through ``/addOrg``."""
        url = (
            f"{DEPOSIT_SERVER}/addOrg?path={encode_query(path)}"
            f"&name={encode_query(name)}&orgName={encode_query(org_name)}"
        )
        self._call("POST", url, content_type="application/json")

    def add_person(
        self,
        path: str,
        name: str,
        first_name: str,
        last_name: str,
        affiliation: str,
    ) -> None:
        """Add one principal investigator through ``/addPerson``."""
        display = f"{first_name} {last_name}".strip()
        url = (
            f"{DEPOSIT_SERVER}/addPerson?path={encode_query(path)}"
            f"&name={encode_query(name)}"
            f"&personFirstName={encode_query(first_name)}"
            f"&personLastName={encode_query(last_name)}"
            f"&personName={encode_query(display)}"
        )
        if affiliation:
            url += f"&personOrgName={encode_query(affiliation)}"
        self._call("POST", url, content_type="application/json")

    def add_date_range(self, path: str, label: str, start: str, end: str) -> None:
        """Add the project time period through ``/addDateRange``."""
        url = (
            f"{DEPOSIT_SERVER}/addDateRange?path={encode_query(path)}"
            f"&startDate={encode_query(start)}&endDate={encode_query(end)}"
            f"&label={encode_query(label or 'timePeriod')}"
        )
        self._call("POST", url, content_type="application/json")

    def suggest_subject_terms(self, term: str) -> list[str]:
        """Return subject-term suggestions for ``term``."""
        url = f"{DEPOSIT_SERVER}/suggestSubjectTerms?term={encode_query(term)}&page=1"
        return suggestion_texts(self._call("GET", url))

    def _call(
        self,
        method: str,
        url: str,
        data: dict[str, str] | None = None,
        content_type: str | None = None,
    ) -> Any:
        """Perform one deposit request and return parsed JSON when the body is JSON."""
        request: dict[str, Any] = {"url": url, "method": method}
        if data is not None:
            request["data"] = data
        if content_type:
            request["contentType"] = content_type
        result = self._page.evaluate(AJAX_JS, request)
        status = int(result.get("status") or 0)
        body_text = redact_secrets(str(result.get("body") or ""))
        append_deposit_log(
            self._log_path, method, url, status, result.get("elapsedMs"), body_text
        )
        if status < 200 or status >= 300:
            path = urlsplit(url).path
            raise RuntimeError(f"Deposit {method} {path} failed ({status}): {body_text[:300]}")
        return _parse_body(body_text)


def _project_path(body: Any) -> str:
    """Read ``/datalumos/{id}`` from a createProject response."""
    if not isinstance(body, dict):
        raise RuntimeError(f"createProject returned an unexpected body: {body!r}"[:300])
    new_path = str(body.get("newPath") or "").strip()
    if not new_path and body.get("id"):
        new_path = f"{HOME_PATH}/{body.get('id')}"
    if not new_path.startswith(f"{HOME_PATH}/"):
        raise RuntimeError(f"createProject did not return a project path: {body!r}"[:300])
    return new_path


def _parse_body(body_text: str) -> Any:
    """Return JSON when the body parses, otherwise the raw text."""
    if not body_text.strip():
        return None
    try:
        return json.loads(body_text)
    except json.JSONDecodeError:
        return body_text
