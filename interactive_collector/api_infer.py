"""POST /api/infer-metadata: suggest metadata from the summary and downloaded files."""

from pathlib import Path
from typing import Any

from flask import request

from interactive_collector.api_projects import get_project_by_drpid
from interactive_collector.collector_state import get_result_by_drpid
from interactive_collector.metadata_inference import infer_project_metadata


def infer_metadata_route() -> Any:
    """
    Return metadata values supported by the project text and downloaded files.

    Does not write the database. The collector fills empty form fields from
    the response so the user can review them before Save.
    """
    payload = request.get_json(silent=True) or {}
    raw = payload.get("drpid", request.form.get("drpid"))
    try:
        drpid = int(raw)
    except (TypeError, ValueError):
        return {"error": "Invalid drpid"}, 400
    project = get_project_by_drpid(drpid)
    if not project:
        return {"error": "Project not found"}, 404
    fields, notes = infer_project_metadata(
        str(project.get("title") or ""),
        str(project.get("summary") or ""),
        _folder_for(drpid, project),
    )
    return {"fields": fields, "notes": notes}


def _folder_for(drpid: int, project: dict[str, Any]) -> Path | None:
    """Prefer the folder the collector opened, then the path stored on the project."""
    state_folder = (get_result_by_drpid().get(drpid, {}).get("folder_path") or "").strip()
    stored_folder = (project.get("folder_path") or "").strip()
    folder_text = state_folder or stored_folder
    return Path(folder_text) if folder_text else None
