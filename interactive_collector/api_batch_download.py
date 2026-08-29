"""
Batch download API: preview data links and download many files with rate limiting.

Streams tab-delimited progress lines compatible with the single-file download protocol,
plus BATCH, JOB, STATUS, and BATCH_DONE lines for orchestration.
"""

from __future__ import annotations

import time
from typing import Generator, List, Optional, Set

from interactive_collector.api_download import generate_download_progress
from interactive_collector.api_scoreboard import get_scoreboard_urls
from interactive_collector.batch_download_state import (
    BatchDownloadJob,
    cancel_batch_download_job,
    create_batch_download_job,
    get_batch_download_job,
    pause_batch_download_job,
    remove_batch_download_job,
    resume_batch_download_job,
)
from interactive_collector.data_link_utils import (
    extract_data_links_from_html,
    filter_urls_not_in_scoreboard,
    is_data_file_url,
)
from utils.url_utils import fetch_page_body, is_valid_url

DEFAULT_BATCH_DELAY_SEC = 1.5
_PAUSE_POLL_SEC = 0.35


def preview_data_links_from_page_url(page_url: str) -> tuple[List[str], Optional[str]]:
    """
    Fetch a catalog page and return data-file links found in main content.

    Returns:
        (links, error_message). error_message is set on fetch/parse failure.
    """
    url = (page_url or "").strip()
    if not url or not is_valid_url(url):
        return [], "valid page URL is required"
    status, body, _ct, _logical = fetch_page_body(url)
    if status != 200 or not body:
        return [], f"Could not fetch page (HTTP {status})"
    links = extract_data_links_from_html(body, url)
    return links, None


def resolve_batch_urls(
    page_url: Optional[str],
    explicit_urls: Optional[List[str]],
    skip_existing: bool,
) -> tuple[List[str], Optional[str]]:
    """
    Build the URL list for a batch job from explicit urls and/or page fetch.

    Returns:
        (urls, error_message).
    """
    urls: List[str] = []
    if explicit_urls:
        for raw in explicit_urls:
            u = (raw or "").strip()
            if u and is_data_file_url(u):
                urls.append(u)
    if not urls and page_url:
        urls, err = preview_data_links_from_page_url(page_url)
        if err:
            return [], err
    if not urls:
        return [], "No data file links found"
    seen: Set[str] = set()
    unique: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    if skip_existing:
        board = set(get_scoreboard_urls())
        unique = filter_urls_not_in_scoreboard(unique, board)
    if not unique:
        return [], "All links were already on the scoreboard"
    return unique, None


def _wait_while_paused(job: BatchDownloadJob) -> Generator[str, None, bool]:
    """
    Yield STATUS lines while paused. Returns False if cancelled, True to continue.
    """
    while job.paused and not job.cancelled:
        yield "STATUS\tpaused\n"
        time.sleep(_PAUSE_POLL_SEC)
    return not job.cancelled


def generate_batch_download_progress(
    urls: List[str],
    folder_path: str,
    drpid: int,
    referrer: Optional[str],
    delay_sec: float = DEFAULT_BATCH_DELAY_SEC,
    job: Optional[BatchDownloadJob] = None,
) -> Generator[str, None, None]:
    """
    Download each URL sequentially with delay_sec between files.

    Yields JOB, BATCH, per-file SAVING/PROGRESS/DONE/ERROR, STATUS when paused,
    CANCELLED when stopped, and BATCH_DONE when finished.
    """
    owned_job = job is None
    if job is None:
        job = create_batch_download_job()
    job_id = job.job_id
    total = len(urls)
    yield f"JOB\t{job_id}\n"
    yield f"BATCH\t0\t{total}\n"
    completed = 0
    try:
        for index, url in enumerate(urls):
            if job.cancelled:
                yield "CANCELLED\tuser cancelled\n"
                return
            if not (yield from _wait_while_paused(job)):
                yield "CANCELLED\tuser cancelled\n"
                return
            yield f"BATCH\t{index + 1}\t{total}\t{url}\n"
            for line in generate_download_progress(url, folder_path, drpid, referrer):
                if line.startswith("ERROR\t"):
                    yield line
                    break
                yield line
                if line.startswith("DONE\t"):
                    completed += 1
                    break
            if job.cancelled:
                yield "CANCELLED\tuser cancelled\n"
                return
            if index + 1 < total:
                if not (yield from _wait_while_paused(job)):
                    yield "CANCELLED\tuser cancelled\n"
                    return
                time.sleep(max(0.0, delay_sec))
        yield f"BATCH_DONE\t{completed}\t{total}\n"
    finally:
        if owned_job:
            remove_batch_download_job(job_id)


def control_batch_download(job_id: str, action: str) -> tuple[bool, Optional[str]]:
    """
    Pause, resume, or cancel a batch job.

    Args:
        job_id: Job identifier from JOB line.
        action: One of pause, resume, cancel.

    Returns:
        (ok, error_message).
    """
    action = (action or "").strip().lower()
    if action == "pause":
        ok = pause_batch_download_job(job_id)
        return (ok, None if ok else "Unknown job")
    if action == "resume":
        ok = resume_batch_download_job(job_id)
        return (ok, None if ok else "Unknown job")
    if action == "cancel":
        ok = cancel_batch_download_job(job_id)
        return (ok, None if ok else "Unknown job")
    return False, f"Invalid action: {action}"
