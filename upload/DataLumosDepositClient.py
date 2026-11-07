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
from upload.deposit_direct import (
    deposit_request,
    parse_body,
    prepare_deposit_token,
    project_path,
)
from upload.deposit_field_match import suggestion_texts
from upload.deposit_page_request import (
    AJAX_JS,
    DEPOSIT_SERVER,
    HOME_PATH,
    append_deposit_log,
    encode_query,
    redact_secrets,
)
from utils.Logger import Logger


class DataLumosDepositClient:
    """Deposit API calls for one authenticated Playwright page."""

    def __init__(
        self,
        page: Page,
        log_path: Path | None = None,
        token: str = "",
    ) -> None:
        """
        Args:
            page: Playwright page that will be logged into DataLumos.
            log_path: Optional JSONL file for redacted request summaries.
            token: Bearer token already read for this browser session.
        """
        self._page = page
        self._log_path = log_path
        self._token: str | None = token or None
        self._ready = bool(self._token)

    @property
    def token(self) -> str:
        """Bearer token for this client, empty after a rejected response."""
        return self._token or ""

    def ensure_deposit_page(self, reporter: Any = None) -> None:
        """Prepare a bearer token, rendering the workspace only when it is missing."""
        if self._ready and self._token:
            return
        self._token = prepare_deposit_token(self._page, reporter)
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
        return project_path(self._call("POST", url, content_type="application/json"))

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

    def delete_path(self, path: str) -> None:
        """
        Delete a deposit file, folder, or project via ``DELETE /deletePath``.

        Args:
            path: Resource path such as ``/datalumos/{id}`` for a project.

        Raises:
            RuntimeError: When the HTTP status is not 2xx, or the JSON body
                includes an ``errorCode`` (e.g. published projects).
        """
        url = f"{DEPOSIT_SERVER}/deletePath?path={encode_query(path)}"
        body = self._call("DELETE", url)
        if isinstance(body, dict) and body.get("errorCode"):
            message = body.get("errorMessage") or body.get("errorCode")
            raise RuntimeError(f"Deposit DELETE /deletePath rejected {path}: {message}")

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
        result = self._dispatch(method, url, data, content_type, request)
        status = int(result.get("status") or 0)
        if status == 401:
            self._forget_token()
        body_text = redact_secrets(str(result.get("body") or ""))
        append_deposit_log(
            self._log_path, method, url, status, result.get("elapsedMs"), body_text
        )
        if status < 200 or status >= 300:
            path = urlsplit(url).path
            raise RuntimeError(f"Deposit {method} {path} failed ({status}): {body_text[:300]}")
        return parse_body(body_text)

    def _dispatch(
        self,
        method: str,
        url: str,
        data: dict[str, str] | None,
        content_type: str | None,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Call through the browser request context, or the page when no token is saved."""
        if not self._token:
            return self._page.evaluate(AJAX_JS, request)
        try:
            return deposit_request(self._page, self._token, method, url, data, content_type)
        except Exception:
            Logger.info("Deposit request failed")
            return {"status": 0, "body": "", "elapsedMs": 0}

    def _forget_token(self) -> None:
        """Drop a rejected token so the next project reads a new one."""
        self._token = None
        self._ready = False
        try:
            self._page.evaluate("() => { window.jwtToken = ''; }")
        except Exception:
            return
