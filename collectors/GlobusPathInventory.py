"""Recursive Globus endpoint inventory (file counts and total bytes)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from utils.Logger import Logger

ListEntriesFn = Callable[[str, str], list[dict[str, Any]]]


@dataclass(frozen=True)
class GlobusInventorySummary:
    """Aggregate size statistics for a Globus directory tree."""

    endpoint_id: str
    root_path: str
    file_count: int
    dir_count: int
    total_bytes: int


class GlobusPathInventory:
    """Walk a Globus endpoint path via ``operation_ls`` and sum file sizes."""

    def __init__(self, list_entries: ListEntriesFn) -> None:
        """
        Initialize the inventory walker.

        Args:
            list_entries: Callable ``(endpoint_id, path) -> entry dicts``.
        """
        self._list_entries = list_entries

    def summarize(self, endpoint_id: str, root_path: str) -> GlobusInventorySummary:
        """
        Recursively inventory files under a Globus directory path.

        Args:
            endpoint_id: Globus collection UUID.
            root_path: Directory path on the collection.

        Returns:
            File count, directory count, and total byte size.
        """
        normalized_root = self._normalize_dir_path(root_path)
        total_bytes = 0
        file_count = 0
        dir_count = 0
        pending_paths = [normalized_root]
        visited_dirs = 0

        while pending_paths:
            current_path = pending_paths.pop()
            visited_dirs += 1
            if visited_dirs == 1 or visited_dirs % 25 == 0:
                Logger.info(
                    "Globus inventory scanning %s (dirs visited=%s, files=%s)",
                    current_path,
                    visited_dirs,
                    file_count,
                )
            for entry in self._list_entries(endpoint_id, current_path):
                entry_type = str(entry.get("type") or "")
                name = str(entry.get("name") or "")
                if not name:
                    continue
                if entry_type == "file":
                    file_count += 1
                    total_bytes += int(entry.get("size") or 0)
                    continue
                if entry_type == "dir":
                    dir_count += 1
                    pending_paths.append(self._join_dir_path(current_path, name))

        return GlobusInventorySummary(
            endpoint_id=endpoint_id,
            root_path=normalized_root,
            file_count=file_count,
            dir_count=dir_count,
            total_bytes=total_bytes,
        )

    @staticmethod
    def _normalize_dir_path(path: str) -> str:
        """Ensure a Globus directory path starts and ends with ``/``."""
        normalized = path.strip() or "/"
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        if not normalized.endswith("/"):
            normalized = f"{normalized}/"
        return normalized

    @staticmethod
    def _join_dir_path(parent_path: str, name: str) -> str:
        """Join a parent directory path with a child directory name."""
        parent = parent_path.rstrip("/")
        child = name.strip("/")
        return f"{parent}/{child}/"
