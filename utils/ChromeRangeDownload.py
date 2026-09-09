"""
Download large files with Chrome TLS impersonation and HTTP Range chunks.

ROSA P (Akamai) returns 403 to aria2/requests and often truncates single-stream
browser downloads around ~1 GB. Chrome-impersonated Range requests succeed and
can resume past that cutoff. HTTP/1.1 is forced because HTTP/2 streams often
fail with PROTOCOL_ERROR on ranges past ~1 GiB. Mid-chunk disconnects (curl 18)
keep any bytes already written and continue from the new offset.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from utils.file_utils import format_file_size
from utils.Logger import Logger
from utils.url_utils import BROWSER_HEADERS

DEFAULT_RANGE_CHUNK_BYTES = 256 * 1024 * 1024
POST_1GIB_CHUNK_BYTES = 4 * 1024 * 1024
MIN_CHUNK_BYTES = 256 * 1024
ONE_GIB = 1024 * 1024 * 1024
DEFAULT_CHUNK_TIMEOUT_SEC = 180
DEFAULT_CHUNK_RETRIES = 40
SMALL_RANGE_BYTES = 2 * 1024 * 1024


class PartialRangeReceived(Exception):
    """Raised when a Range transfer stops early after writing some bytes."""

    def __init__(self, written: int, expected: int, start: int, end: int) -> None:
        self.written = written
        self.expected = expected
        self.start = start
        self.end = end
        super().__init__(
            f"Partial Range {start}-{end}: wrote {written} of {expected} bytes"
        )


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


def _is_transport_error(exc: BaseException) -> bool:
    """Return True for curl transport failures worth a fresh session."""
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "protocol_error",
            "http/2",
            "curl: (92)",
            "curl: (56)",
            "curl: (28)",
            "curl: (18)",
            "bytes missing",
            "connection reset",
            "failed to perform",
            "partial range",
            "timed out",
            "timeout",
        )
    )


def _chrome_session() -> Any:
    """Create a curl_cffi session that impersonates Chrome over HTTP/1.1."""
    from curl_cffi import requests as cf
    from curl_cffi.const import CurlHttpVersion

    session = cf.Session(
        impersonate="chrome",
        http_version=CurlHttpVersion.V1_1,
    )
    session.headers.update(
        {
            "User-Agent": BROWSER_HEADERS["User-Agent"],
            "Accept": BROWSER_HEADERS.get("Accept", "*/*"),
            "Accept-Language": BROWSER_HEADERS.get("Accept-Language", "en-US,en;q=0.9"),
        }
    )
    return session


def _close_session(session: Any | None) -> None:
    """Close a curl_cffi session when present."""
    if session is None:
        return
    close = getattr(session, "close", None)
    if callable(close):
        close()


def probe_content_length(url: str, *, session: Any | None = None) -> Optional[int]:
    """
    Return remote size via Range ``bytes=0-0`` Content-Range (preferred) or HEAD.

    Args:
        url: File URL.
        session: Optional existing curl_cffi session.

    Returns:
        Size in bytes, or None when unavailable.
    """
    owns_session = session is None
    client = session or _chrome_session()
    referer = referer_for_file_url(url)
    try:
        ranged = client.get(
            url,
            headers={"Referer": referer, "Range": "bytes=0-0"},
            allow_redirects=True,
            timeout=60,
        )
        content_range = ranged.headers.get("Content-Range") or ranged.headers.get(
            "content-range"
        )
        ranged.close()
        if content_range and "/" in content_range:
            total_raw = content_range.rsplit("/", 1)[-1].strip()
            if total_raw != "*":
                return int(total_raw)

        response = client.head(
            url,
            headers={"Referer": referer},
            allow_redirects=True,
            timeout=60,
        )
        if response.status_code >= 400:
            return None
        raw = response.headers.get("Content-Length") or response.headers.get(
            "content-length"
        )
        if not raw:
            return None
        return int(raw)
    except (TypeError, ValueError, OSError) as exc:
        Logger.debug("Chrome size probe failed for %s: %s", url, exc)
        return None
    finally:
        if owns_session:
            _close_session(client)


def _initial_chunk_size(offset: int, configured: int) -> int:
    """Pick the starting Range size for this offset."""
    if offset >= ONE_GIB:
        return min(configured, POST_1GIB_CHUNK_BYTES)
    return configured


def _shrink_chunk_size(current: int) -> int:
    """Halve chunk size down to the minimum after transfer failures."""
    return max(MIN_CHUNK_BYTES, current // 2)


def _truncate_to(dest: Path, offset: int) -> None:
    """Truncate ``dest`` to ``offset`` bytes when it is longer."""
    if dest.is_file() and dest.stat().st_size > offset:
        with open(dest, "rb+") as handle:
            handle.truncate(offset)


def _append_bytes(dest: Path, data: bytes) -> int:
    """Append ``data`` to ``dest`` and return the byte count."""
    if not data:
        return 0
    with open(dest, "ab") as handle:
        handle.write(data)
    return len(data)


def _salvage_exception_body(exc: BaseException) -> bytes:
    """Return any partial response body attached to a curl_cffi exception."""
    response = getattr(exc, "response", None)
    if response is None:
        return b""
    content = getattr(response, "content", None)
    if isinstance(content, (bytes, bytearray)) and content:
        return bytes(content)
    return b""


def _download_small_range(
    session: Any,
    url: str,
    *,
    start: int,
    end: int,
    dest: Path,
    timeout_sec: int,
) -> int:
    """
    Non-streaming Range GET for small pieces (easier to salvage on curl 18).

    Also tries an open-ended Range if the closed Range fails with no body.
    """
    expected = end - start + 1
    referer = referer_for_file_url(url)
    headers = {"Referer": referer, "Range": f"bytes={start}-{end}"}
    try:
        response = session.get(url, headers=headers, timeout=timeout_sec)
    except Exception as exc:  # noqa: BLE001 - may still have partial body
        salvaged = _salvage_exception_body(exc)[:expected]
        if salvaged:
            written = _append_bytes(dest, salvaged)
            raise PartialRangeReceived(written, expected, start, end) from exc
        raise

    try:
        if response.status_code not in (200, 206):
            raise OSError(f"HTTP {response.status_code} for Range {start}-{end}")
        body = response.content or b""
        if response.status_code == 200:
            if start != 0:
                raise OSError("Server ignored Range (HTTP 200 full body)")
            with open(dest, "wb") as handle:
                handle.write(body)
            return len(body)
        if len(body) > expected:
            body = body[:expected]
        if len(body) == expected:
            return _append_bytes(dest, body)
        if len(body) > 0:
            written = _append_bytes(dest, body)
            raise PartialRangeReceived(written, expected, start, end)
    finally:
        response.close()

    # Closed Range returned empty; try open-ended and take only what we need.
    open_headers = {"Referer": referer, "Range": f"bytes={start}-"}
    response = session.get(
        url, headers=open_headers, stream=True, timeout=timeout_sec
    )
    try:
        if response.status_code not in (200, 206):
            raise OSError(f"HTTP {response.status_code} for open Range at {start}")
        written = 0
        with open(dest, "ab") as handle:
            for chunk in response.iter_content(64 * 1024):
                if not chunk:
                    continue
                need = expected - written
                if need <= 0:
                    break
                piece = chunk[:need]
                handle.write(piece)
                written += len(piece)
                if written >= expected:
                    break
        if written == expected:
            return written
        if written > 0:
            raise PartialRangeReceived(written, expected, start, end)
        raise OSError(f"Open Range at {start} returned 0 bytes")
    finally:
        response.close()


def _stream_to_file(
    response: Any,
    dest: Path,
    *,
    mode: str,
    expected: int | None,
    start: int,
    end: int,
) -> int:
    """
    Stream response body to ``dest``.

    Raises:
        PartialRangeReceived: Transport ended early after writing some bytes.
    """
    written = 0
    try:
        with open(dest, mode) as handle:
            for chunk in response.iter_content(1024 * 1024):
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
    except Exception as exc:  # noqa: BLE001 - convert early close to partial keep
        if written > 0 and _is_transport_error(exc):
            raise PartialRangeReceived(
                written, expected or written, start, end
            ) from exc
        raise

    if expected is not None and written != expected:
        if written > 0:
            raise PartialRangeReceived(written, expected, start, end)
        raise OSError(f"Range {start}-{end} wrote 0 bytes, expected {expected}")
    return written


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
        Number of bytes written (may raise PartialRangeReceived).
    """
    expected = end - start + 1
    if expected <= SMALL_RANGE_BYTES:
        return _download_small_range(
            session,
            url,
            start=start,
            end=end,
            dest=dest,
            timeout_sec=timeout_sec,
        )

    headers = {
        "Referer": referer_for_file_url(url),
        "Range": f"bytes={start}-{end}",
    }
    try:
        response = session.get(
            url, headers=headers, stream=True, timeout=timeout_sec
        )
    except Exception as exc:  # noqa: BLE001 - salvage partial body when present
        salvaged = _salvage_exception_body(exc)[:expected]
        if salvaged:
            written = _append_bytes(dest, salvaged)
            raise PartialRangeReceived(written, expected, start, end) from exc
        raise

    try:
        if response.status_code not in (200, 206):
            raise OSError(f"HTTP {response.status_code} for Range {start}-{end}")

        if response.status_code == 200:
            if start != 0:
                raise OSError(
                    f"Server ignored Range at offset {start} (HTTP 200 full body)"
                )
            raw_len = response.headers.get("Content-Length") or response.headers.get(
                "content-length"
            )
            full_expected = int(raw_len) if raw_len else None
            return _stream_to_file(
                response,
                dest,
                mode="wb",
                expected=full_expected,
                start=start,
                end=end,
            )

        return _stream_to_file(
            response,
            dest,
            mode="ab",
            expected=expected,
            start=start,
            end=end,
        )
    finally:
        response.close()


def _log_progress(offset: int, total: int) -> None:
    """Log download progress at the current offset."""
    Logger.info(
        "Download progress: %s / %s (%.1f%%)",
        format_file_size(offset),
        format_file_size(total),
        100.0 * offset / total,
    )


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

    Resumes partial files. Keeps bytes from mid-chunk disconnects (curl 18) and
    continues from the new offset with smaller Ranges. When Akamai returns 0
    bytes at an offset, backs off longer and keeps retrying.

    Args:
        url: Direct file URL.
        destination_path: Local output path.
        chunk_bytes: Max bytes per Range request (before the post-1GiB cap).
        timeout_sec: Timeout per chunk request.
        max_retries: Retries when a chunk makes no progress.

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
            Logger.info(
                "Already complete on disk: %s (%s)",
                dest.name,
                format_file_size(total),
            )
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
                "Chrome Range download: %s (%s), base chunk %s (HTTP/1.1)",
                dest.name,
                format_file_size(total),
                format_file_size(chunk_bytes),
            )

        offset = existing
        active_chunk = _initial_chunk_size(offset, chunk_bytes)
        stalled_tries = 0
        while offset < total:
            end = min(offset + active_chunk - 1, total - 1)
            try:
                _truncate_to(dest, offset)
                written = _download_one_range(
                    session,
                    url,
                    start=offset,
                    end=end,
                    dest=dest,
                    timeout_sec=timeout_sec,
                )
                offset += written
                if offset > total:
                    _truncate_to(dest, total)
                    offset = total
                stalled_tries = 0
                active_chunk = _initial_chunk_size(offset, chunk_bytes)
                _log_progress(offset, total)
            except PartialRangeReceived as exc:
                offset += exc.written
                stalled_tries = 0
                active_chunk = _shrink_chunk_size(active_chunk)
                Logger.warning(
                    "Kept %s after early close; continuing from %s (next chunk %s)",
                    format_file_size(exc.written),
                    format_file_size(offset),
                    format_file_size(active_chunk),
                )
                _close_session(session)
                session = _chrome_session()
                _log_progress(offset, total)
                time.sleep(1)
            except Exception as exc:  # noqa: BLE001 - retry with smaller chunk
                stalled_tries += 1
                Logger.warning(
                    "Chunk %s-%s attempt %s failed: %s",
                    offset,
                    end,
                    stalled_tries,
                    exc,
                )
                _truncate_to(dest, offset)
                if _is_transport_error(exc):
                    _close_session(session)
                    session = _chrome_session()
                    active_chunk = _shrink_chunk_size(active_chunk)
                if stalled_tries >= max(1, max_retries):
                    Logger.error(
                        "Giving up on %s after chunk failure: %s", dest.name, exc
                    )
                    return (dest.stat().st_size if dest.is_file() else 0, False)
                # Akamai often needs a long cool-down when an offset returns 0 bytes.
                time.sleep(min(5 * stalled_tries, 120))

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
        _close_session(session)
