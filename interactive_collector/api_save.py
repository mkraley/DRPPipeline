"""
API module for save operations (metadata + PDF generation).

Serves: POST /api/save. Updates project metadata in Storage and optionally
generates PDFs for checked scoreboard pages via Playwright (headless Chromium).
Streams progress as SAVING, DONE, ERROR lines.
"""

import json
from pathlib import Path
from typing import Any, Dict, Generator, List

from utils.file_utils import sanitize_filename
from utils.url_utils import is_valid_url


def _folder_extensions_and_size(folder_path: Path) -> tuple[List[str], int]:
    """Return (sorted list of unique extensions without leading dot, total size in bytes)."""
    exts: set[str] = set()
    total = 0
    try:
        for p in folder_path.iterdir():
            if p.is_file():
                total += p.stat().st_size
                if p.suffix:
                    exts.add(p.suffix.lstrip(".").lower())
    except OSError:
        pass
    return (sorted(exts), total)


def _format_file_size(size_bytes: int) -> str:
    """Format byte count as human-friendly string (e.g. '1.2 MB')."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _page_title_or_h1(page: Any) -> str:
    """Get page <title> or first <h1> text from a Playwright page; empty string if neither."""
    try:
        title = page.title()
        if title and (title or "").strip():
            return (title or "").strip()
        try:
            h1 = page.locator("h1").first.text_content(timeout=2000)
            if h1 and (h1 or "").strip():
                return (h1 or "").strip()
        except Exception:
            pass
    except Exception:
        pass
    return ""


def _unique_pdf_basename(base: str, used: Dict[str, int]) -> str:
    """Return a unique sanitized basename: base.pdf or base_1.pdf, base_2.pdf, etc."""
    safe = sanitize_filename(base, max_length=80)
    if not safe:
        safe = "page"
    key = safe.lower()
    n = used.get(key, 0)
    used[key] = n + 1
    if n == 0:
        return f"{safe}.pdf"
    return f"{safe}_{n}.pdf"


def save_metadata(
    drpid: int,
    folder_path_str: str,
    title: str,
    summary: str,
    keywords: str,
    agency: str,
    office: str,
    time_start: str,
    time_end: str,
    download_date: str,
) -> None:
    """
    Update the project record in Storage with metadata and folder stats.

    Args:
        drpid: Project ID.
        folder_path_str: Path to output folder.
        title, summary, keywords, agency, office: Metadata fields.
        time_start, time_end: Date range.
        download_date: When data was downloaded.
    """
    from interactive_collector.collector_state import get_db_path

    # Ensure Storage is initialized (reuse projects module logic).
    try:
        from storage import Storage
        Storage.list_eligible_projects(None, 0)
    except RuntimeError:
        try:
            from utils.Logger import Logger
            if not getattr(Logger, "_initialized", False):
                Logger.initialize(log_level="WARNING")
        except Exception:
            pass
        from storage import Storage
        Storage.initialize("StorageSQLLite", db_path=get_db_path())

    from storage import Storage
    values: Dict[str, Any] = {
        "status": "collector",
        "errors": None,
        "title": title,
        "agency": agency,
        "office": office,
        "summary": summary,
        "keywords": keywords,
        "time_start": time_start,
        "time_end": time_end,
        "download_date": download_date,
    }
    if folder_path_str:
        folder_path = Path(folder_path_str)
        if folder_path.is_dir():
            exts_list, total_bytes = _folder_extensions_and_size(folder_path)
            values["extensions"] = ", ".join(exts_list) if exts_list else ""
            values["file_size"] = _format_file_size(total_bytes)
        else:
            values["extensions"] = ""
            values["file_size"] = ""
    else:
        values["extensions"] = ""
        values["file_size"] = ""
    try:
        Storage.update_record(drpid, values)
    except ValueError:
        pass


def generate_save_progress(
    folder_path: Path,
    urls: List[str],
    indices: List[str],
) -> Generator[str, None, None]:
    """
    Generator that yields progress lines for the PDF save operation.

    Yields: SAVING\\t{url}\\t{current}\\t{total}\\n then DONE\\t{count}\\n or ERROR\\t{msg}\\n
    """
    from playwright.sync_api import sync_playwright

    total = len(indices)
    saved: List[str] = []
    used_basenames: Dict[str, int] = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for current, idx_str in enumerate(indices, 1):
                try:
                    idx = int(idx_str)
                    if idx < 0 or idx >= len(urls):
                        continue
                    url = urls[idx]
                    if not url or not is_valid_url(url):
                        continue
                    yield f"SAVING\t{url}\t{current}\t{total}\n"
                    page = browser.new_page()
                    try:
                        page.goto(url, wait_until="networkidle", timeout=60000)
                        base = _page_title_or_h1(page)
                        if not base:
                            base = "page"
                        pdf_name = _unique_pdf_basename(base, used_basenames)
                        pdf_path = folder_path / pdf_name
                        page.pdf(path=str(pdf_path))
                        saved.append(pdf_name)
                    finally:
                        page.close()
                except (ValueError, Exception) as e:
                    yield f"ERROR\t{str(e)[:200]}\n"
            browser.close()
    except Exception as e:
        yield f"ERROR\t{str(e)[:200]}\n"
    yield f"DONE\t{len(saved)}\n"
