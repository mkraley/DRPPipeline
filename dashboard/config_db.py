"""Resolve the active SQLite DB from config.json for the dashboard."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from storage.NextStep import next_step_for_status
from utils.Args import Args

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _PROJECT_ROOT / "config.json"


def _status_label(status: str) -> str:
    """
    Format ``status → next_step`` for the dashboard status pane.

    Args:
        status: Project status value (or ``(null)``).
    """
    if status == "(null)":
        return "(null) → ?"
    nxt = next_step_for_status(status)
    if nxt is None:
        nxt_text = "done"
    else:
        nxt_text = nxt
    return f"{status} → {nxt_text}"


def load_config_data(config_path: Path | None = None) -> dict[str, Any]:
    """
    Load and flatten ``config.json`` the same way ``Args`` does.

    Args:
        config_path: Config file path; defaults to project ``config.json``.

    Returns:
        Flattened config dict (globals + selected ``sources.<name>``).

    Raises:
        FileNotFoundError: If the config file is missing.
        ValueError: If JSON is invalid or layers cannot be resolved.
    """
    path = config_path if config_path is not None else _DEFAULT_CONFIG
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8-sig") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"Config file '{path}' must contain a JSON object")
    return Args._resolve_config_layers(raw)


def resolve_db_path(
    config_path: Path | None = None,
) -> tuple[str, Path]:
    """
    Return ``(source_name, absolute_db_path)`` from the active config source.

    Args:
        config_path: Optional override for ``config.json``.

    Returns:
        Source key and absolute path to the SQLite database.
    """
    path = config_path if config_path is not None else _DEFAULT_CONFIG
    flat = load_config_data(path)
    source = str(flat.get("source") or "")
    db_value = flat.get("db_path") or "drp_pipeline.db"
    db_path = Path(str(db_value))
    if not db_path.is_absolute():
        db_path = path.parent / db_path
    return source, db_path.resolve()


def pipeline_stats(config_path: Path | None = None) -> dict[str, Any]:
    """
    Aggregate project counts for the DB selected by ``config.json``.

    Args:
        config_path: Optional override for ``config.json``.

    Returns:
        Dict with ``source``, ``db_path``, ``total``, ``with_errors``,
        ``with_warnings``, and ``by_status`` (list of ``{status, count}``).
    """
    source, db_path = resolve_db_path(config_path)
    result: dict[str, Any] = {
        "source": source,
        "db_path": str(db_path),
        "total": 0,
        "with_errors": 0,
        "with_warnings": 0,
        "by_status": [],
        "error": None,
    }
    if not db_path.is_file():
        result["error"] = f"Database not found: {db_path}"
        return result
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            result["total"] = con.execute(
                "SELECT COUNT(*) FROM projects"
            ).fetchone()[0]
            result["with_errors"] = con.execute(
                "SELECT COUNT(*) FROM projects "
                "WHERE errors IS NOT NULL AND errors != ''"
            ).fetchone()[0]
            result["with_warnings"] = con.execute(
                "SELECT COUNT(*) FROM projects "
                "WHERE warnings IS NOT NULL AND warnings != ''"
            ).fetchone()[0]
            rows = con.execute(
                "SELECT status, COUNT(*) AS n FROM projects "
                "GROUP BY status ORDER BY n DESC"
            ).fetchall()
            result["by_status"] = [
                {
                    "status": row["status"] or "(null)",
                    "next_step": (
                        None
                        if (row["status"] or "") == ""
                        else next_step_for_status(row["status"])
                    ),
                    "label": _status_label(row["status"] or "(null)"),
                    "count": row["n"],
                }
                for row in rows
            ]
        finally:
            con.close()
    except sqlite3.Error as exc:
        result["error"] = str(exc)
    return result
