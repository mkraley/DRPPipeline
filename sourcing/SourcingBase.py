"""
Shared base class and helpers for DRP Pipeline sourcing modules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from duplicate_checking import DuplicateChecker
from utils.Logger import Logger


class SourcingBase(ABC):
    """
    Base class for batch sourcing modules invoked by the orchestrator with ``run(-1)``.
    """

    @abstractmethod
    def run(self, drpid: int) -> None:
        """
        Enumerate candidate URLs and create storage records.

        Args:
            drpid: Orchestrator convention; batch sourcing modules use -1.
        """

    @classmethod
    def ensure_batch_drpid(cls, drpid: int, module_name: str) -> None:
        """
        Log when ``run`` is called with a project DRPID instead of batch mode.

        Args:
            drpid: DRPID passed by the orchestrator.
            module_name: Class name for log context.
        """
        if drpid != -1:
            Logger.warning(
                "%s ignores DRPID %s; batch enumeration uses run(-1).",
                module_name,
                drpid,
            )

    @staticmethod
    def format_id_range(assigned_ids: list[int]) -> str:
        """
        Format an assigned DRPID list for completion log lines.

        Args:
            assigned_ids: DRPIDs created during the run.

        Returns:
            Empty string, `` (DRPID: n)``, or `` (DRPIDs: low-high)``.
        """
        if not assigned_ids:
            return ""
        low, high = min(assigned_ids), max(assigned_ids)
        if low == high:
            return f" (DRPID: {low})"
        return f" (DRPIDs: {low}-{high})"

    @staticmethod
    def is_duplicate_in_storage(url: str, checker: DuplicateChecker) -> bool:
        """
        Return True when ``url`` is already stored and log the skip.

        Args:
            url: Candidate source URL.
            checker: Duplicate checker bound to current Storage.

        Returns:
            True when the URL should be skipped.
        """
        if checker.exists_in_storage(url):
            Logger.error(
                "Duplicate source URL already in storage, skipping (no row created): %s",
                url,
            )
            return True
        return False
