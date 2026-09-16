"""
Build googleapiclient Sheets v4 services with optional custom TLS CA bundle.

Corporate proxies / TLS inspection often present a chain Python does not trust
(“unable to get local issuer certificate”). Set `ssl_ca_bundle` in config to a
PEM file that includes your organization’s root (or a combined bundle).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional, Union

from utils.Logger import Logger

Credentials = Any

_truststore_injected = False

# Google Sheets "Read requests per minute per user" is typically 60/min.
DEFAULT_SHEETS_429_MAX_RETRIES = 6
DEFAULT_SHEETS_429_INITIAL_BACKOFF_SECONDS = 60.0
DEFAULT_SHEETS_429_MAX_BACKOFF_SECONDS = 120.0


def sheets_retry_after_seconds(exc: BaseException, fallback: float) -> float:
    """
    Return seconds to wait after a Sheets API 429.

    Prefers the ``Retry-After`` response header when present; otherwise uses
    ``fallback`` (at least 60s to align with per-minute read quotas).

    Args:
        exc: Raised ``HttpError`` (or compatible) with optional ``resp``.
        fallback: Backoff seconds for this attempt when no header is present.

    Returns:
        Seconds to sleep before retrying.
    """
    resp = getattr(exc, "resp", None)
    raw: Optional[str] = None
    if resp is not None:
        getter = getattr(resp, "get", None)
        if callable(getter):
            raw = getter("retry-after") or getter("Retry-After")
        elif hasattr(resp, "headers"):
            headers = resp.headers
            raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is not None:
        try:
            return max(float(raw), 1.0)
        except (TypeError, ValueError):
            pass
    return max(float(fallback), 60.0)


def execute_sheets_request(
    request: Any,
    *,
    max_retries: int = DEFAULT_SHEETS_429_MAX_RETRIES,
    initial_backoff_seconds: float = DEFAULT_SHEETS_429_INITIAL_BACKOFF_SECONDS,
    max_backoff_seconds: float = DEFAULT_SHEETS_429_MAX_BACKOFF_SECONDS,
    operation_label: str = "Google Sheets API",
) -> Any:
    """
    Execute a googleapiclient request, retrying HTTP 429 with backoff.

    Args:
        request: Object with an ``execute()`` method (Sheets API request).
        max_retries: Extra attempts after the first failure.
        initial_backoff_seconds: Base wait when Retry-After is absent.
        max_backoff_seconds: Cap for exponential backoff.
        operation_label: Text included in warning logs.

    Returns:
        The value returned by ``request.execute()``.

    Raises:
        HttpError: When a non-429 error occurs, or 429 retries are exhausted.
    """
    try:
        from googleapiclient.errors import HttpError
    except ImportError as exc:  # pragma: no cover - dependency missing
        raise RuntimeError(
            "google-api-python-client is required for Sheets API calls"
        ) from exc

    delay = initial_backoff_seconds
    attempts = max_retries + 1
    last_error: Optional[BaseException] = None

    for attempt in range(attempts):
        try:
            return request.execute()
        except HttpError as exc:
            last_error = exc
            status = getattr(getattr(exc, "resp", None), "status", None)
            try:
                status_int = int(status) if status is not None else None
            except (TypeError, ValueError):
                status_int = None
            if status_int != 429 or attempt >= attempts - 1:
                raise
            wait_seconds = sheets_retry_after_seconds(exc, delay)
            Logger.warning(
                "%s rate limited (429); retry %s/%s in %.0fs",
                operation_label,
                attempt + 1,
                max_retries,
                wait_seconds,
            )
            time.sleep(wait_seconds)
            delay = min(delay * 2.0, max_backoff_seconds)

    assert last_error is not None
    raise last_error


def _ensure_system_trust_store() -> None:
    """Use the OS certificate store when no custom CA bundle is configured."""
    global _truststore_injected
    if _truststore_injected:
        return
    try:
        import truststore

        truststore.inject_into_ssl()
        _truststore_injected = True
    except ImportError:
        pass


def build_sheets_v4_service(
    credentials: Credentials,
    *,
    cache_discovery: bool = False,
    ssl_ca_bundle: Optional[Union[str, Path]] = None,
) -> Any:
    """
    Return a Sheets API v4 service object.

    When ``ssl_ca_bundle`` is a path to an existing PEM file, requests use
    httplib2 with that CA bundle (via :class:`google_auth_httplib2.AuthorizedHttp`).
    When None, uses :func:`Args.ssl_ca_bundle` if Args is initialized; otherwise
    injects ``truststore`` (OS certificate store) when available, then uses the
    default Google client.

    Args:
        credentials: ``google.auth.credentials.Credentials`` (e.g. service account).
        cache_discovery: Passed through to discovery ``build``.
        ssl_ca_bundle: Explicit CA bundle path; overrides Args when set.

    Returns:
        The result of ``googleapiclient.discovery.build('sheets', 'v4', ...)``.
    """
    from googleapiclient.discovery import build

    bundle_path = _resolve_ssl_ca_bundle_path(ssl_ca_bundle)
    if bundle_path is not None:
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp

        http = httplib2.Http(ca_certs=str(bundle_path))
        authorized = AuthorizedHttp(credentials, http=http)
        return build("sheets", "v4", http=authorized, cache_discovery=cache_discovery)

    _ensure_system_trust_store()
    return build(
        "sheets",
        "v4",
        credentials=credentials,
        cache_discovery=cache_discovery,
    )


def _resolve_ssl_ca_bundle_path(
    explicit: Optional[Union[str, Path]],
) -> Optional[Path]:
    """Pick CA bundle path: explicit arg, then Args.ssl_ca_bundle, then None."""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit).expanduser())
    try:
        from utils.Args import Args

        if Args._initialized and getattr(Args, "ssl_ca_bundle", None):
            candidates.append(Path(str(Args.ssl_ca_bundle)).expanduser())
    except Exception:
        pass
    for p in candidates:
        if p.is_file():
            return p.resolve()
    return None
