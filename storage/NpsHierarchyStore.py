"""
SQLite tables for the NPS IRMA Program → Project → Product tree.

Generic ``projects`` rows remain one DataLumos project per IRMA Project.
These tables store the extra hierarchy the collector will walk later.
"""

from __future__ import annotations

import sqlite3
from typing import Any


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nps_projects (
    irma_project_id INTEGER PRIMARY KEY,
    drpid INTEGER NOT NULL UNIQUE,
    irma_collection_id INTEGER NOT NULL,
    irma_program_id INTEGER NOT NULL,
    collection_title TEXT,
    program_title TEXT,
    project_title TEXT,
    breadcrumb TEXT,
    public_file_count INTEGER NOT NULL DEFAULT 0,
    product_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_nps_projects_drpid ON nps_projects(drpid);
CREATE INDEX IF NOT EXISTS idx_nps_projects_program ON nps_projects(irma_program_id);

CREATE TABLE IF NOT EXISTS nps_products (
    irma_product_id INTEGER PRIMARY KEY,
    irma_project_id INTEGER NOT NULL,
    drpid INTEGER NOT NULL,
    title TEXT,
    reference_type TEXT,
    source_url TEXT,
    visibility TEXT,
    file_access TEXT,
    public_file_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_nps_products_project ON nps_products(irma_project_id);
CREATE INDEX IF NOT EXISTS idx_nps_products_drpid ON nps_products(drpid);
"""


class NpsHierarchyStore:
    """Read and write NPS hierarchy rows on a Storage SQLite connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """
        Bind to an open SQLite connection.

        Args:
            connection: Connection that already has the projects table.
        """
        self._connection = connection
        self.ensure_schema(connection)

    @classmethod
    def from_storage(cls) -> "NpsHierarchyStore":
        """
        Build a store from the initialized Storage singleton.

        Returns:
            Store bound to the live SQLite connection.
        """
        from storage import Storage
        from storage.StorageSQLLite import StorageSQLLite

        instance = Storage._instance
        if not isinstance(instance, StorageSQLLite):
            raise TypeError("NPS hierarchy requires StorageSQLLite.")
        return cls(instance.sqlite_connection())

    @staticmethod
    def ensure_schema(connection: sqlite3.Connection) -> None:
        """
        Create NPS hierarchy tables and indexes when missing.

        Args:
            connection: Open SQLite connection.
        """
        connection.executescript(_SCHEMA_SQL)
        connection.commit()

    def upsert_project(self, row: dict[str, Any]) -> None:
        """
        Insert or replace one IRMA Project hierarchy row.

        Args:
            row: Columns matching ``nps_projects``.
        """
        self._connection.execute(
            """
            INSERT OR REPLACE INTO nps_projects (
                irma_project_id, drpid, irma_collection_id, irma_program_id,
                collection_title, program_title, project_title, breadcrumb,
                public_file_count, product_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(row["irma_project_id"]),
                int(row["drpid"]),
                int(row["irma_collection_id"]),
                int(row["irma_program_id"]),
                row.get("collection_title") or "",
                row.get("program_title") or "",
                row.get("project_title") or "",
                row.get("breadcrumb") or "",
                int(row.get("public_file_count") or 0),
                int(row.get("product_count") or 0),
            ),
        )
        self._connection.commit()

    def replace_products(self, irma_project_id: int, products: list[dict[str, Any]]) -> None:
        """
        Replace product rows for one IRMA Project.

        Args:
            irma_project_id: Parent IRMA Project reference id.
            products: Product dicts to store.
        """
        self._connection.execute(
            "DELETE FROM nps_products WHERE irma_project_id = ?",
            (int(irma_project_id),),
        )
        for product in products:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO nps_products (
                    irma_product_id, irma_project_id, drpid, title,
                    reference_type, source_url, visibility, file_access,
                    public_file_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(product["irma_product_id"]),
                    int(irma_project_id),
                    int(product["drpid"]),
                    product.get("title") or "",
                    product.get("reference_type") or "",
                    product.get("source_url") or "",
                    product.get("visibility") or "",
                    product.get("file_access") or "",
                    int(product.get("public_file_count") or 0),
                ),
            )
        self._connection.commit()

    def get_project(self, irma_project_id: int) -> dict[str, Any] | None:
        """Return one nps_projects row by IRMA Project id, or None."""
        return self._fetchone_dict(
            "SELECT * FROM nps_projects WHERE irma_project_id = ?",
            (int(irma_project_id),),
        )

    def get_project_by_drpid(self, drpid: int) -> dict[str, Any] | None:
        """Return one nps_projects row by DRPID, or None."""
        return self._fetchone_dict(
            "SELECT * FROM nps_projects WHERE drpid = ?",
            (int(drpid),),
        )

    def list_products(self, irma_project_id: int) -> list[dict[str, Any]]:
        """Return product rows for one IRMA Project id."""
        return self._fetchall_dicts(
            "SELECT * FROM nps_products WHERE irma_project_id = ? ORDER BY irma_product_id",
            (int(irma_project_id),),
        )

    def list_products_for_drpid(self, drpid: int) -> list[dict[str, Any]]:
        """Return product rows for one Storage DRPID."""
        return self._fetchall_dicts(
            "SELECT * FROM nps_products WHERE drpid = ? ORDER BY irma_product_id",
            (int(drpid),),
        )

    def update_public_file_count(self, drpid: int, public_file_count: int) -> None:
        """Set nps_projects.public_file_count to the recursive collected file total."""
        self._connection.execute(
            "UPDATE nps_projects SET public_file_count = ? WHERE drpid = ?",
            (int(public_file_count), int(drpid)),
        )
        self._connection.commit()

    def _fetchone_dict(self, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        """Run a SELECT and return one row as a dict."""
        cursor = self._connection.execute(query, params)
        fetched = cursor.fetchone()
        if fetched is None:
            return None
        names = [item[0] for item in cursor.description]
        return dict(zip(names, fetched))

    def _fetchall_dicts(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        """Run a SELECT and return all rows as dicts."""
        cursor = self._connection.execute(query, params)
        names = [item[0] for item in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]
