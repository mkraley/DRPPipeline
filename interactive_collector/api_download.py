"""
API module for file downloads.

Serves: POST /api/download-file. Downloads non-HTML URLs (PDF, CSV, etc.)
to the project output folder and streams progress (SAVING, PROGRESS, DONE).
Adds a download entry to the scoreboard on completion.
"""

from pathlib import Path
from typing import Any, Dict, Generator, Optional

import requests

from utils.file_utils import sanitize_filename
from utils.url_utils import BROWSER_HEADERS, is_valid_url

# Content-Type to file extension (lowercase type -> extension with dot).
_CONTENT_TYPE_EXT: Dict[str, str] = {
    "application/pdf": ".pdf",
    "text/csv": ".csv",
    "application/csv": ".csv",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/json": ".json",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "text/plain": ".txt",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

# Progress report interval for large file downloads (MB).
_DOWNLOAD_PROGRESS_INTERVAL_MB = 50.0


def _extension_from_content_type(content_type: Optional[str]) -> str:
    """Return extension with leading dot from Content-Type, or empty string."""
    if not content_type or ";" in content_type:
        content_type = (content_type or "").split(";")[0].strip().lower()
    return _CONTENT_TYPE_EXT.get(content_type, "")


def _filename_from_content_disposition(header_value: Optional[str]) -> Optional[str]:
    """Extract filename from Content-Disposition header (filename= or filename*=)."""
    if not header_value:
        return None
    if "filename*=" in header_value:
        try:
            part = header_value.split("filename*=")[-1].strip().strip(";")
            if part.lower().startswith("utf-8''"):
                from urllib.parse import unquote
                return unquote(part[7:])
            return part.strip("\"'")
        except Exception:
            pass
    if "filename=" in header_value:
        try:
            part = header_value.split("filename=", 1)[-1].strip().strip(";").strip("\"'")
            if part:
                return part
        except Exception:
            pass
    return None


def _filename_from_url(url: str) -> str:
    """Last path segment or 'download'."""
    from urllib.parse import urlparse, unquote
    path = urlparse(url).path or ""
    name = (path.rstrip("/").split("/")[-1] or "download")
    return unquote(name)


def _unique_download_basename(base: str, ext: str, used: Dict[str, int]) -> str:
    """Return unique sanitized basename: base.ext or base_1.ext, etc."""
    if not base or base == "download":
        base = "download"
    base = sanitize_filename(base, max_length=80)
    if ext and not base.lower().endswith(ext.lower()):
        base = base + ext
    key = base.lower()
    n = used.get(key, 0)
    used[key] = n + 1
    if n == 0:
        return base
    if "." in base:
        stem, suffix = base.rsplit(".", 1)
        return f"{stem}_{n}.{suffix}"
    return f"{base}_{n}"


def generate_download_progress(
    url: str,
    folder_path_str: str,
    drpid: int,
    referrer: Optional[str],
) -> Generator[str, None, None]:
    """
    Generator that yields progress lines for a single file download.

    Yields: SAVING\\t{basename}\\n, PROGRESS\\t{written}\\t{total}\\n,
    then DONE\\t{basename}\\t{size}\\t{ext}\\n or ERROR\\t{msg}\\n.
    """
    from interactive_collector.api_scoreboard import add_download
    from interactive_collector.collector_state import get_result_by_drpid

    folder_path = Path(folder_path_str)
    if not folder_path.is_dir():
        yield "ERROR\tOutput folder not found\n"
        return
    try:
        resp = requests.get(url, stream=True, headers=BROWSER_HEADERS, timeout=(30, 300))
        resp.raise_for_status()
    except requests.RequestException as e:
        yield f"ERROR\t{str(e)[:200]}\n"
        return

    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
    content_disp = resp.headers.get("Content-Disposition")
    content_length: Optional[int] = None
    try:
        cl = resp.headers.get("Content-Length")
        if cl is not None:
            content_length = int(cl)
    except ValueError:
        pass

    filename = _filename_from_content_disposition(content_disp) or _filename_from_url(url)
    ext = _extension_from_content_type(content_type)
    if filename and "." in filename:
        pass
    else:
        if ext and filename:
            filename = filename + (ext if ext.startswith(".") else "." + ext)
        elif ext:
            filename = "download" + (ext if ext.startswith(".") else "." + ext)
    base = filename
    if "." in base:
        base = base.rsplit(".", 1)[0]
        ext_from_name = "." + filename.rsplit(".", 1)[-1]
        if not ext:
            ext = ext_from_name
    else:
        if not ext:
            ext = ""

    used: Dict[str, int] = {p.name.lower(): 1 for p in folder_path.iterdir() if p.is_file()}
    basename = _unique_download_basename(base, ext, used)
    dest = folder_path / basename

    yield f"SAVING\t{basename}\n"
    chunk_size = 1024 * 1024  # 1 MB
    written = 0
    last_yield_mb = 0.0
    try:
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
                mb = written / (1024 * 1024)
                if (mb - last_yield_mb) >= _DOWNLOAD_PROGRESS_INTERVAL_MB or (
                    content_length and written >= content_length
                ):
                    last_yield_mb = mb
                    total_str = str(content_length) if content_length is not None else ""
                    yield f"PROGRESS\t{written}\t{total_str}\n"
    except OSError as e:
        yield f"ERROR\t{str(e)[:200]}\n"
        return

    ext_display = ext.lstrip(".")
    yield f"DONE\t{basename}\t{written}\t{ext_display}\n"

    get_result_by_drpid().setdefault(drpid, {}).setdefault("downloads", []).append({
        "url": url,
        "path": str(dest),
        "size": written,
        "extension": ext_display,
        "filename": basename,
    })
    add_download(url, referrer, str(dest), written, ext_display, filename=basename)
