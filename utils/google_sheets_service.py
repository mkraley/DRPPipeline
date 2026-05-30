"""
Build googleapiclient Sheets v4 services with optional custom TLS CA bundle.

Corporate proxies / TLS inspection often present a chain Python does not trust
(“unable to get local issuer certificate”). Set `ssl_ca_bundle` in config to a
PEM file that includes your organization’s root (or a combined bundle).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

Credentials = Any

_truststore_injected = False


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
