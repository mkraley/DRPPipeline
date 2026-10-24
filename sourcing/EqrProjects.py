"""Insert the seven Electric Quarterly Report CSV projects."""

from __future__ import annotations

from typing import Any

from collectors.EqrProjectRange import EqrProjectRange, project_ranges
from collectors.FercKeywords import keywords_for_ferc
from sourcing.FercCandidateFetcher import AGENCY
from storage import Storage


def eqr_storage_fields(span: EqrProjectRange) -> dict[str, Any]:
    """
    Return the Storage fields for one EQR span.

    Args:
        span: Quarter range for the project.

    Returns:
        Fields written when the project is sourced.
    """
    title = span.title()
    return {
        "title": title,
        "summary": span.summary(),
        "agency": AGENCY,
        "keywords": keywords_for_ferc(title),
        "time_start": span.time_start(),
        "time_end": span.time_end(),
        "geographic_coverage": "United States",
        "data_types": "Administrative records data",
        "status": "sourced",
    }


def insert_missing_eqr_projects() -> list[int]:
    """
    Insert EQR projects whose source URLs are not already stored.

    Returns:
        DRPIDs inserted on this call. Existing URLs are left unchanged.
    """
    inserted: list[int] = []
    for span in project_ranges():
        source_url = span.source_url()
        if Storage.exists_by_source_url(source_url):
            continue
        drpid = Storage.create_record(source_url)
        Storage.update_record(drpid, eqr_storage_fields(span))
        inserted.append(drpid)
    return inserted
