"""
Per-project catalog file rows for large and xlarge collection.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS project_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drpid INTEGER NOT NULL,
    relative_path TEXT NOT NULL,
    size_bytes INTEGER,
    source_url TEXT,
    downloaded INTEGER NOT NULL DEFAULT 0,
    uploaded INTEGER NOT NULL DEFAULT 0,
    UNIQUE(drpid, relative_path)
);
CREATE INDEX IF NOT EXISTS idx_project_files_drpid ON project_files(drpid);
"""


@dataclass(frozen=True)
class ProjectFileRow:
    """One catalog file tracked for a large or xlarge project."""

    drpid: int
    relative_path: str
    size_bytes: int | None
    source_url: str
    downloaded: bool
    uploaded: bool


class ProjectFileStore:
    """Read and replace ``project_files`` rows for one pipeline database."""

    @staticmethod
    def ensure_schema(connection: sqlite3.Connection) -> None:
        """Create ``project_files`` when it is missing."""
        connection.executescript(_SCHEMA_SQL)
        connection.commit()

    def __init__(self, connection: sqlite3.Connection) -> None:
        """
        Bind the store to an open SQLite connection.

        Args:
            connection: Connection opened by ``StorageSQLLite``.
        """
        self._connection = connection

    @classmethod
    def from_storage(cls) -> "ProjectFileStore":
        """Return a store using the active Storage connection."""
        from storage import Storage
        from storage.StorageSQLLite import StorageSQLLite

        instance = Storage._instance
        if not isinstance(instance, StorageSQLLite):
            raise TypeError("project_files requires StorageSQLLite.")
        return cls(instance.sqlite_connection())

    def replace_for_project(self, drpid: int, rows: list[ProjectFileRow]) -> None:
        """Replace every file row for ``drpid``."""
        self._connection.execute(
            "DELETE FROM project_files WHERE drpid = ?",
            (int(drpid),),
        )
        self._connection.executemany(
            """
            INSERT INTO project_files (
                drpid, relative_path, size_bytes, source_url, downloaded, uploaded
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(row.drpid),
                    row.relative_path,
                    row.size_bytes,
                    row.source_url,
                    1 if row.downloaded else 0,
                    1 if row.uploaded else 0,
                )
                for row in rows
            ],
        )
        self._connection.commit()

    def delete_for_project(self, drpid: int) -> None:
        """Remove file rows when a project is no longer large or xlarge."""
        self._connection.execute(
            "DELETE FROM project_files WHERE drpid = ?",
            (int(drpid),),
        )
        self._connection.commit()

    def list_for_project(self, drpid: int) -> list[ProjectFileRow]:
        """Return file rows for ``drpid`` in path order."""
        cursor = self._connection.execute(
            """
            SELECT drpid, relative_path, size_bytes, source_url, downloaded, uploaded
            FROM project_files
            WHERE drpid = ?
            ORDER BY relative_path
            """,
            (int(drpid),),
        )
        return [_row_from_sql(row) for row in cursor.fetchall()]

    def list_pending_downloads(self, drpid: int) -> list[ProjectFileRow]:
        """Return rows that still need to be fetched."""
        return [row for row in self.list_for_project(drpid) if not row.downloaded]

    def list_pending_uploads(self, drpid: int) -> list[ProjectFileRow]:
        """Return downloaded rows that have not been sent to DataLumos."""
        return [
            row
            for row in self.list_for_project(drpid)
            if row.downloaded and not row.uploaded
        ]

    def mark_downloaded(
        self,
        drpid: int,
        relative_path: str,
        size_bytes: int | None,
    ) -> None:
        """Mark one file present on disk at its expected size."""
        self._connection.execute(
            """
            UPDATE project_files
            SET downloaded = 1,
                size_bytes = COALESCE(?, size_bytes)
            WHERE drpid = ? AND relative_path = ?
            """,
            (size_bytes, int(drpid), relative_path),
        )
        self._connection.commit()

    def mark_uploaded(self, drpid: int, relative_paths: list[str]) -> None:
        """Mark files that the first or resume upload has sent."""
        self._connection.executemany(
            """
            UPDATE project_files
            SET uploaded = 1
            WHERE drpid = ? AND relative_path = ?
            """,
            [(int(drpid), path) for path in relative_paths],
        )
        self._connection.commit()


def _row_from_sql(row: Any) -> ProjectFileRow:
    """Map a SQLite tuple to a ``ProjectFileRow``."""
    return ProjectFileRow(
        drpid=int(row[0]),
        relative_path=str(row[1]),
        size_bytes=None if row[2] is None else int(row[2]),
        source_url=str(row[3] or ""),
        downloaded=bool(row[4]),
        uploaded=bool(row[5]),
    )
