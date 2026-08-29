"""
In-memory state for interactive collector batch download jobs (pause / resume / cancel).
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class BatchDownloadJob:
    """Mutable flags for one streaming batch download."""

    job_id: str
    paused: bool = False
    cancelled: bool = False


_lock = threading.Lock()
_jobs: Dict[str, BatchDownloadJob] = {}


def create_batch_download_job() -> BatchDownloadJob:
    """Register a new batch download job and return it."""
    job_id = str(uuid.uuid4())
    job = BatchDownloadJob(job_id=job_id)
    with _lock:
        _jobs[job_id] = job
    return job


def get_batch_download_job(job_id: str) -> Optional[BatchDownloadJob]:
    """Return the job for job_id, or None if unknown."""
    with _lock:
        return _jobs.get(job_id)


def pause_batch_download_job(job_id: str) -> bool:
    """Set paused on the job. Returns False if job_id is unknown."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return False
        job.paused = True
        return True


def resume_batch_download_job(job_id: str) -> bool:
    """Clear paused on the job. Returns False if job_id is unknown."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return False
        job.paused = False
        return True


def cancel_batch_download_job(job_id: str) -> bool:
    """Cancel the job. Returns False if job_id is unknown."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return False
        job.cancelled = True
        job.paused = False
        return True


def remove_batch_download_job(job_id: str) -> None:
    """Remove job from registry after the stream completes."""
    with _lock:
        _jobs.pop(job_id, None)
