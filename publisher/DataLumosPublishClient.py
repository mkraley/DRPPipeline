"""
Publish one DataLumos project through the deposit HTTP API.

The browser is only the cookie jar and bearer token. Inventory, terms, and
publish are requests to ``deposit.icpsr.umich.edu``. Endpoints are the ones
``deposit.min.js`` (build 20260910-150211) calls from Publish Data and the
Storage Status panel.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import Page

from publisher.WorkspaceFileStats import WorkspaceStorageStatus, storage_status_from_api
from publisher.publish_terms import (
    PUBLISH_URL,
    apply_publish_answers,
    license_list_url,
    public_domain_license_id,
    resource_path,
    review_terms_url,
    term_attribute_names,
    terms_attributes_url,
    terms_url,
    view_storage_url,
)
from upload.deposit_direct import deposit_request, parse_body, prepare_deposit_token
from upload.deposit_page_request import append_deposit_record, redact_secrets
from utils.Logger import Logger

_VIEW_ATTEMPTS = 18
_VIEW_PAUSE_SECONDS = 5
_REQUEST_TIMEOUT_MS = 120000
_PUBLIC_VIEW_MARKER = "Published Versions"


class DataLumosPublishClient:
    """Deposit API calls that publish one already-uploaded project."""

    def __init__(self, page: Page, log_path: Path | None = None) -> None:
        """
        Args:
            page: Playwright page whose cookie jar is logged into DataLumos.
            log_path: Optional JSONL file for redacted request and response text.
        """
        self._page = page
        self._token = ""
        self._log_path = log_path

    def ensure_ready(self) -> None:
        """Read a bearer token, rendering the workspace only when it is missing."""
        if self._token:
            return
        self._token = prepare_deposit_token(self._page)

    def storage_status(self, workspace_id: str) -> WorkspaceStorageStatus:
        """Return file count and space from ``viewStorage``."""
        path = resource_path(workspace_id)
        payload = self._get(view_storage_url(path))
        return storage_status_from_api(payload)

    def publish_project(self, workspace_id: str, version_title: str | None = None) -> None:
        """POST the terms dialog answers for ``workspace_id``."""
        path = resource_path(workspace_id)
        started = time.perf_counter()
        body = self._publish_body(path, version_title)
        self._post(PUBLISH_URL, body)
        elapsed = time.perf_counter() - started
        Logger.info("Deposit API publish took %.1fs for %s", elapsed, workspace_id)

    def view_is_public(self, url: str) -> bool:
        """
        Return True when a browser load of the view URL is the public project.

        Uses a second page so the deposit token page stays put. Playwright's
        request client is blocked by the DataLumos edge; a headed navigation is not.
        The public page can appear after the publish POST returns, so this retries.
        """
        checker = self._page.context.new_page()
        try:
            return self._view_becomes_public(checker, url)
        finally:
            checker.close()

    def _view_becomes_public(self, page: Page, url: str) -> bool:
        """Reload the view URL until it is public or the attempts are used."""
        for attempt in range(_VIEW_ATTEMPTS):
            if self._view_page_ok(page, url):
                return True
            if attempt + 1 < _VIEW_ATTEMPTS:
                time.sleep(_VIEW_PAUSE_SECONDS)
        return False

    def _publish_body(self, path: str, version_title: str | None) -> dict[str, Any]:
        """Load terms and licenses, then apply the fixed DataLumos answers."""
        resource = self._get(terms_url(path))
        review_terms = self._get(review_terms_url(path))
        questions = term_attribute_names(self._get(terms_attributes_url(path)))
        license_id = public_domain_license_id(self._get(license_list_url(path)))
        return apply_publish_answers(
            resource, review_terms, questions, license_id, version_title
        )

    def _get(self, url: str) -> Any:
        """GET one deposit URL and return parsed JSON."""
        self.ensure_ready()
        result = deposit_request(self._page, self._token, "GET", url)
        self._log("GET", url, result, "")
        return self._accepted("GET", url, result)

    def _post(self, url: str, payload: dict[str, Any]) -> Any:
        """POST JSON and return parsed JSON."""
        self.ensure_ready()
        body = json.dumps(payload, separators=(",", ":"))
        result = deposit_request(
            self._page,
            self._token,
            "POST",
            url,
            content_type="application/json",
            body=body,
        )
        self._log("POST", url, result, body)
        return self._accepted("POST", url, result)

    def _log(self, method: str, url: str, result: dict[str, Any], request_body: str) -> None:
        """Append method, path, status, and redacted bodies when a log file is set."""
        if self._log_path is None:
            return
        response = redact_secrets(str(result.get("body") or ""))
        append_deposit_record(
            self._log_path,
            {
                "method": method,
                "path": urlsplit(url).path,
                "status": int(result.get("status") or 0),
                "elapsedMs": result.get("elapsedMs"),
                "requestBody": redact_secrets(request_body)[:4000],
                "responseBody": response[:1500],
            },
        )

    def _accepted(self, method: str, url: str, result: dict[str, Any]) -> Any:
        """Return a 2xx body. A 401 drops the token so the caller can sign in again."""
        status = int(result.get("status") or 0)
        path = urlsplit(url).path
        Logger.info(
            "Deposit %s %s -> %s in %sms",
            method,
            path,
            status,
            result.get("elapsedMs"),
        )
        body_text = redact_secrets(str(result.get("body") or ""))
        if status == 401:
            self._token = ""
            raise RuntimeError(f"Deposit {method} {path} failed (401)")
        if status < 200 or status >= 300:
            raise RuntimeError(
                f"Deposit {method} {path} failed ({status}): {body_text[:300]}"
            )
        return parse_body(body_text)

    def _view_page_ok(self, page: Page, url: str) -> bool:
        """Return True when one navigation lands on the published project page."""
        response = page.goto(url, wait_until="domcontentloaded", timeout=_REQUEST_TIMEOUT_MS)
        final = str(page.url or url).lower()
        status = 0 if response is None else int(response.status)
        Logger.info("Public view %s -> %s", status, final[:180])
        if status != 200 or "login" in final or "__cf_chl" in final:
            return False
        return _PUBLIC_VIEW_MARKER in page.content()
