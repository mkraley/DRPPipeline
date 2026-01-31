"""
Download a URL to a file with progress logging and optional resume.

Used when the download URL is known (e.g. captured from Playwright) so we can
stream with requests, log progress, and resume on failure.
"""

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import requests

from utils.file_utils import format_file_size
from utils.Logger import Logger


def _cookies_to_dict(cookies: Optional[Union[List[Any], Dict[str, str]]]) -> Dict[str, str]:
    """Convert Playwright-style cookies (list of objects with name/value) or dict to requests dict."""
    if not cookies:
        return {}
    if isinstance(cookies, dict):
        return cookies
    out: Dict[str, str] = {}
    for c in cookies:
        name = getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else None)
        value = getattr(c, "value", None) or (c.get("value") if isinstance(c, dict) else None)
        if name is not None and value is not None:
            out[str(name)] = str(value)
    return out


def download_via_url(
    url: str,
    destination_path: Path,
    cookies: Optional[Union[List[Any], Dict[str, str]]] = None,
    headers: Optional[Dict[str, str]] = None,
    progress_interval_mb: float = 50.0,
    progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    resume: bool = True,
    timeout_sec: Optional[int] = None,
    session: Optional[requests.Session] = None,
) -> Tuple[int, bool]:
    """
    Download url to destination_path with optional progress and resume.

    Args:
        url: Download URL (must support GET; optional Range for resume).
        destination_path: Full path for the output file.
        cookies: Cookies for the request (e.g. from page.context.cookies()).
        headers: Optional extra headers (e.g. X-App-Token for Socrata).
        progress_interval_mb: Log/callback every N MB (0 = only at start/end).
        progress_callback: Optional callback(bytes_so_far, total_or_none).
        resume: If True and file exists, try to resume with Range header.
        timeout_sec: Per-read timeout; None = no timeout.
        session: Optional requests.Session (uses requests.get if None).

    Returns:
        (bytes_written, success).
    """
    cookie_dict = _cookies_to_dict(cookies)
    dest = Path(destination_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    existing_size = dest.stat().st_size if dest.exists() else 0
    start_byte = existing_size if resume and existing_size else 0
    request_headers: Dict[str, str] = dict(headers) if headers else {}
    if start_byte > 0:
        request_headers["Range"] = f"bytes={start_byte}-"

    get = (session or requests).get
    timeout_val = (timeout_sec or 30, timeout_sec or 300)
    try:
        resp = get(
            url,
            stream=True,
            cookies=cookie_dict,
            headers=request_headers or None,
            timeout=timeout_val,
        )
        resp.raise_for_status()
    except requests.HTTPError:
        # Re-raise so caller can handle 403/401 (e.g. fall back to browser session)
        raise
    except requests.RequestException as e:
        Logger.error("Download request failed: %s", e)
        return (0, False)

    # If we requested Range but got 200, server doesn't support resume; write from 0
    if start_byte > 0 and resp.status_code == 200:
        start_byte = 0
        written = 0
    else:
        written = start_byte

    total_from_header: Optional[int] = None
    if "Content-Range" in resp.headers:
        cr = resp.headers.get("Content-Range", "")
        if "/" in cr:
            try:
                total_from_header = int(cr.split("/")[-1].strip())
            except ValueError:
                pass
    elif "Content-Length" in resp.headers:
        try:
            cl = int(resp.headers["Content-Length"])
            total_from_header = start_byte + cl
        except ValueError:
            pass

    total: Optional[int] = total_from_header
    last_log_mb = written / (1024 * 1024)
    chunk_size = 1024 * 1024  # 1 MB
    start_time = time.perf_counter()
    mode = "ab" if start_byte > 0 else "wb"

    try:
        with open(dest, mode) as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
                mb = written / (1024 * 1024)
                if progress_interval_mb > 0 and (mb - last_log_mb) >= progress_interval_mb:
                    last_log_mb = mb
                    if progress_callback:
                        progress_callback(written, total)
                    else:
                        if total is not None:
                            pct = 100.0 * written / total if total else 0
                            Logger.info(
                                "Download progress: %s / %s (%.1f%%)",
                                format_file_size(written),
                                format_file_size(total),
                                pct,
                            )
                        else:
                            Logger.info("Download progress: %s received", format_file_size(written))
        elapsed = time.perf_counter() - start_time
        rate = (written - start_byte) / (1024 * 1024) / elapsed if elapsed > 0 else 0
        Logger.info(
            "Download complete: %s in %.1f s (%.2f MB/s)",
            format_file_size(written),
            elapsed,
            rate,
        )
        return (written, True)
    except OSError as e:
        Logger.error("Download write failed: %s", e)
        return (written, False)
