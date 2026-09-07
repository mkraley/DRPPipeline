"""
Download large files with Chrome TLS impersonation and HTTP Range chunks.

ROSA P (Akamai) returns 403 to aria2/requests and often truncates single-stream
browser downloads around ~1 GB. Chrome-impersonated Range requests succeed and
can resume past that cutoff.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from utils.file_utils import format_file_size
from utils.Logger import Logger
from utils.url_utils import BROWSER_HEADERS

# Stay under the ~1.1 GB single-stream cutoff observed on ROSA P / Akamai.
DEFAULT_RANGE_CHUNK_BYTES = 256 * 1024 * 1024
DEFAULT_CHUNK_TIMEOUT_SEC = 600
DEFAULT_CHUNK_RETRIES = 3


def requires_chrome_range_download(url: str) -> bool:
    """
    Return True when plain HTTP clients are blocked and long streams truncate.

    ROSA P (BTS) is fronted by Akamai: aria2/requests get 403, and single-stream
    browser downloads often stop around 1 GB. Chrome-impersonated Range chunks work.
    """
    host = (urlparse(url).hostname or "").lower()
    return host == "rosap.ntl.bts.gov" or host.endswith(".rosap.ntl.bts.gov")


def referer_for_file_url(url: str) -> str:
    """
    Return a Referer URL for a direct file download link.

    ``.../view/dot/7547/file.zip`` → ``.../view/dot/7547``
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    parent = path.rsplit("/", 1)[0] if "/" in path else path
    return f"{parsed.scheme}://{parsed.netloc}{parent}"


def _chrome_session() -> Any:
    """Create a curl_cffi session that impersonates Chrome."""
    from curl_cffi import requests as cf

    session = cf.Session(impersonate="chrome")
    session.headers.update(
        {
            "User-Agent": BROWSER_HEADERS["User-Agent"],
            "Accept": BROWSER_HEADERS.get("Accept", "*/*"),
            "Accept-Language": BROWSER_HEADERS.get("Accept-Language", "en-US,en;q=0.9"),
        }
    )
    return session


def probe_content_length(url: str, *, session: Any | None = None) -> Optional[int]:
    """
    Return Content-Length via Chrome-impersonated HEAD, or None.

    Args:
        url: File URL.
        session: Optional existing curl_cffi session.

    Returns:
        Size in bytes, or None when unavailable.
    """
    owns_session = session is None
    client = session or _chrome_session()
    try:
        response = client.head(
            url,
            headers={"Referer": referer_for_file_url(url)},
            allow_redirects=True,
            timeout=60,
        )
        if response.status_code >= 400:
            return None
        raw = response.headers.get("Content-Length")
        if not raw:
            return None
        return int(raw)
    except (TypeError, ValueError, OSError) as exc:
        Logger.debug("Chrome HEAD Content-Length failed for %s: %s", url, exc)
        return None
    finally:
        if owns_session:
            client.close()


def _download_one_range(
    session: Any,
    url: str,
    *,
    start: int,
    end: int,
    dest: Path,
    timeout_sec: int,
) -> int:
    """
    GET one inclusive byte range and append it to ``dest``.

    Returns:
        Number of bytes written.
    """
    headers = {
        "Referer": referer_for_file_url(url),
        "Range": f"bytes={start}-{end}",
    }
    response = session.get(url, headers=headers, stream=True, timeout=timeout_sec)
    if response.status_code not in (200, 206):
        response.close()
        raise OSError(f"HTTP {response.status_code} for Range {start}-{end}")

    expected = end - start + 1
    written = 0
    with open(dest, "ab") as handle:
        for chunk in response.iter_content(1024 * 1024):
            if not chunk:
                continue
            handle.write(chunk)
            written += len(chunk)
    response.close()
    if written != expected:
        raise OSError(
            f"Range {start}-{end} wrote {written} bytes, expected {expected}"
        )
    return written


def download_via_chrome_ranges(
    url: str,
    destination_path: Path,
    *,
    chunk_bytes: int = DEFAULT_RANGE_CHUNK_BYTES,
    timeout_sec: int = DEFAULT_CHUNK_TIMEOUT_SEC,
    max_retries: int = DEFAULT_CHUNK_RETRIES,
) -> tuple[int, bool]:
    """
    Download ``url`` in Range chunks with Chrome TLS impersonation.

    Resumes when ``destination_path`` already has a partial file shorter than
    the remote Content-Length.

    Args:
        url: Direct file URL.
        destination_path: Local output path.
        chunk_bytes: Max bytes per Range request.
        timeout_sec: Timeout per chunk request.
        max_retries: Retries per failed chunk.

    Returns:
        ``(bytes_on_disk, success)``.
    """
    dest = Path(destination_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    session = _chrome_session()
    try:
        total = probe_content_length(url, session=session)
        if total is None or total <= 0:
            Logger.error("Could not determine remote size for %s", url)
            return (dest.stat().st_size if dest.is_file() else 0, False)

        existing = dest.stat().st_size if dest.is_file() else 0
        if existing > total:
            Logger.warning(
                "Local file larger than remote (%s > %s); re-downloading %s",
                format_file_size(existing),
                format_file_size(total),
                dest.name,
            )
            dest.unlink(missing_ok=True)
            existing = 0
        if existing == total:
            Logger.info("Already complete on disk: %s (%s)", dest.name, format_file_size(total))
            return total, True

        if existing > 0:
            Logger.info(
                "Resuming %s at %s / %s",
                dest.name,
                format_file_size(existing),
                format_file_size(total),
            )
        else:
            Logger.info(
                "Chrome Range download: %s (%s) in %s chunks",
                dest.name,
                format_file_size(total),
                format_file_size(chunk_bytes),
            )

        offset = existing
        while offset < total:
            end = min(offset + chunk_bytes - 1, total - 1)
            last_error: Exception | None = None
            for attempt in range(1, max(1, max_retries) + 1):
                try:
                    # Truncate any partial failed append from a prior attempt.
                    if dest.is_file() and dest.stat().st_size > offset:
                        with open(dest, "rb+") as handle:
                            handle.truncate(offset)
                    written = _download_one_range(
                        session,
                        url,
                        start=offset,
                        end=end,
                        dest=dest,
                        timeout_sec=timeout_sec,
                    )
                    offset += written
                    Logger.info(
                        "Download progress: %s / %s (%.1f%%)",
                        format_file_size(offset),
                        format_file_size(total),
                        100.0 * offset / total,
                    )
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001 - retry then fail
                    last_error = exc
                    Logger.warning(
                        "Chunk %s-%s attempt %s failed: %s",
                        offset,
                        end,
                        attempt,
                        exc,
                    )
                    time.sleep(min(2 * attempt, 10))
            if last_error is not None:
                Logger.error("Giving up on %s after chunk failure: %s", dest.name, last_error)
                return (dest.stat().st_size if dest.is_file() else 0, False)

        final_size = dest.stat().st_size if dest.is_file() else 0
        if final_size != total:
            Logger.error(
                "Size mismatch for %s: got %s, expected %s",
                dest.name,
                format_file_size(final_size),
                format_file_size(total),
            )
            return final_size, False
        return final_size, True
    finally:
        session.close()
