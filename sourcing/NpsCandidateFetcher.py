"""
Enumerate NPS IRMA Projects with anonymously downloadable Digital Files.
"""

from __future__ import annotations

import time
from typing import Any

from sourcing.NpsCatalogClient import NpsCatalogClient
from sourcing.NpsProjectMapper import build_candidate_row, profile_title
from sourcing.NpsReferenceRules import profile_children, reference_id_of
from utils.Args import Args
from utils.Logger import Logger

DEFAULT_COLLECTION_ID = 9688
DEFAULT_PROGRAM_ID = 2310251


class NpsCandidateFetcher:
    """Walk Collection → Program → Project and emit sourcing rows."""

    def __init__(
        self,
        *,
        client: NpsCatalogClient | None = None,
        request_delay: float | None = None,
        collection_id: int | None = None,
        program_id: int | None = None,
    ) -> None:
        """
        Initialize the fetcher.

        Args:
            client: IRMA client (created when omitted).
            request_delay: Seconds between HTTP calls.
            collection_id: IRMA Collection; defaults to ``nps_collection_id``.
            program_id: IRMA Program; 0 means all programs in the collection.
        """
        self._client = client or NpsCatalogClient()
        default_delay = float(getattr(Args, "nps_request_delay", 0.1) or 0.1)
        self._request_delay = request_delay if request_delay is not None else default_delay
        self._collection_id = (
            collection_id
            if collection_id is not None
            else int(getattr(Args, "nps_collection_id", DEFAULT_COLLECTION_ID) or DEFAULT_COLLECTION_ID)
        )
        self._program_id = (
            program_id
            if program_id is not None
            else int(getattr(Args, "nps_program_id", DEFAULT_PROGRAM_ID) or 0)
        )

    def list_project_rows(self) -> list[dict[str, Any]]:
        """
        Return IRMA Projects that have at least one public Digital File.

        Returns:
            Candidate rows ready for Storage plus hierarchy product lists.
        """
        collection = self._client.fetch_collection(self._collection_id)
        collection_title = str(collection.get("Title") or collection.get("title") or "")
        programs = self._selected_programs()
        rows: list[dict[str, Any]] = []
        seen_projects: set[int] = set()
        for program in programs:
            rows.extend(
                self._rows_for_program(collection_title, program, seen_projects)
            )
        return rows

    def close(self) -> None:
        """Release the underlying catalog client."""
        self._client.close()

    def _selected_programs(self) -> list[dict[str, Any]]:
        """Return Collection Program rows, optionally filtered to one Program."""
        programs = self._client.fetch_collection_programs(self._collection_id)
        if self._program_id <= 0:
            return programs
        matched = [row for row in programs if reference_id_of(row) == self._program_id]
        if not matched:
            raise ValueError(
                f"IRMA Program {self._program_id} is not in Collection {self._collection_id}."
            )
        return matched

    def _rows_for_program(
        self,
        collection_title: str,
        program_row: dict[str, Any],
        seen_projects: set[int],
    ) -> list[dict[str, Any]]:
        """Fetch one Program profile and emit downloadable Project rows."""
        program_id = reference_id_of(program_row)
        if program_id is None:
            return []
        self._pause()
        program_profile = self._client.fetch_profile(program_id)
        program_title = profile_title(program_profile) or str(program_row.get("Title") or "")
        rows: list[dict[str, Any]] = []
        for child in profile_children(program_profile):
            row = self._row_for_project(
                collection_title, program_id, program_title, child, seen_projects
            )
            if row is not None:
                rows.append(row)
        Logger.info(
            "NPS sourcing: program %s (%s) yielded %s downloadable project(s)",
            program_id,
            program_title,
            len(rows),
        )
        return rows

    def _row_for_project(
        self,
        collection_title: str,
        program_id: int,
        program_title: str,
        child: dict[str, Any],
        seen_projects: set[int],
    ) -> dict[str, Any] | None:
        """Fetch one Project profile and map it when it has public files."""
        project_id = reference_id_of(child)
        if project_id is None or project_id in seen_projects:
            return None
        seen_projects.add(project_id)
        self._pause()
        try:
            profile = self._client.fetch_profile(project_id)
        except RuntimeError as exc:
            Logger.error("NPS sourcing: skip Project %s (%s)", project_id, exc)
            return None
        return build_candidate_row(
            collection_id=self._collection_id,
            collection_title=collection_title,
            program_id=program_id,
            program_title=program_title,
            profile=profile,
        )

    def _pause(self) -> None:
        """Sleep between IRMA requests when a delay is configured."""
        if self._request_delay > 0:
            time.sleep(self._request_delay)
