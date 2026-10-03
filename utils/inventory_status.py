"""
Collected-project size classes shared by every source collector.

Totals use the full catalog inventory. Cutoffs are 1 GiB and 25 GiB.
"""

from __future__ import annotations

MAX_COLLECTED_BYTES = 1 * 1024**3
XLARGE_MIN_BYTES = 25 * 1024**3

STATUS_COLLECTED = "collected"
STATUS_COLLECTED_LARGE = "collected - large"
STATUS_COLLECTED_XLARGE = "collected - xlarge"
STATUS_UPLOADED = "uploaded"
STATUS_UPLOADED_LARGE = "uploaded - large"
STATUS_UPLOADED_XLARGE = "uploaded - xlarge"
STATUS_RESIZE_WAIT = "resize wait"
STATUS_RESIZED = "resized"
STATUS_DOWNLOADED = "downloaded"
STATUS_FINISH_WAIT = "finish wait"

COLLECTED_SIZE_STATUSES = frozenset({
    STATUS_COLLECTED,
    STATUS_COLLECTED_LARGE,
    STATUS_COLLECTED_XLARGE,
})
DEFERRED_COLLECT_STATUSES = frozenset({
    STATUS_COLLECTED_LARGE,
    STATUS_COLLECTED_XLARGE,
})


def classify_collected_status(known_bytes: int, *, has_unknown_size: bool) -> str:
    """
    Return the collected status for a project's full inventory size.

    Args:
        known_bytes: Sum of catalog sizes that are known, plus on-disk sizes
            used when a downloaded file had no catalog size.
        has_unknown_size: True when any referenced file still has no size.

    Returns:
        ``collected``, ``collected - large``, or ``collected - xlarge``.
    """
    if known_bytes >= XLARGE_MIN_BYTES:
        return STATUS_COLLECTED_XLARGE
    if has_unknown_size:
        return STATUS_COLLECTED_XLARGE
    if known_bytes > MAX_COLLECTED_BYTES:
        return STATUS_COLLECTED_LARGE
    return STATUS_COLLECTED


def upload_status_for_collected(collected_status: str) -> str:
    """
    Return the status written after the first DataLumos upload.

    Args:
        collected_status: Status before upload.

    Returns:
        Matching uploaded status. Unclassified values stay ``uploaded``.
    """
    if collected_status == STATUS_COLLECTED_XLARGE:
        return STATUS_UPLOADED_XLARGE
    if collected_status == STATUS_COLLECTED_LARGE:
        return STATUS_UPLOADED_LARGE
    return STATUS_UPLOADED


def skips_upload_file_count(status: str) -> bool:
    """
    Return True when ``num_files`` includes files that were not uploaded yet.

    Args:
        status: Project status before or during the first upload.
    """
    compact = status.casefold().replace(" ", "").replace("-", "")
    return compact in {
        "collectedlarge",
        "collectedxlarge",
        "collectedlargefile",
        "uploadedlarge",
        "uploadedxlarge",
        "uploadedlargefile",
    }
