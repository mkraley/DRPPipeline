"""
Flask Blueprint for Interactive Collector JSON API.

Serves the SPA with: projects, load-page, scoreboard, save, download-file.
"""

import json
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, request

from interactive_collector.api_download import generate_download_progress
from interactive_collector.api_pages import load_page, prepare_page_content
from interactive_collector.api_projects import (
    ensure_output_folder,
    folder_path_for_drpid,
    get_first_eligible,
    get_next_eligible_after,
    get_project_by_drpid,
)
from interactive_collector.api_save import generate_save_progress, save_metadata
from interactive_collector.api_scoreboard import add_to_scoreboard, clear_scoreboard, get_scoreboard_tree, get_scoreboard_urls
from interactive_collector.collector_state import get_result_by_drpid
from utils.url_utils import is_valid_url

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _str_or_none(x: Any) -> str | None:
    """Return stripped string or None if missing/empty."""
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None


@api_bp.route("/projects/first", methods=["GET"])
def projects_first() -> Any:
    """
    Return the first eligible project (prereq=sourcing, no errors).

    Returns:
        JSON project dict or 404.
    """
    proj = get_first_eligible()
    if not proj:
        return {"error": "No eligible project"}, 404
    return proj


@api_bp.route("/projects/next", methods=["GET"])
def projects_next() -> Any:
    """
    Return the next eligible project after current_drpid.

    Query: current_drpid (required).

    Returns:
        JSON project dict or 404.
    """
    current = request.args.get("current_drpid", "").strip()
    if not current:
        return {"error": "current_drpid required"}, 400
    try:
        current_drpid = int(current)
    except ValueError:
        return {"error": "Invalid current_drpid"}, 400
    proj = get_next_eligible_after(current_drpid)
    if not proj:
        return {"error": "No next project"}, 404
    return proj


@api_bp.route("/projects/<int:drpid>", methods=["GET"])
def projects_get(drpid: int) -> Any:
    """
    Return the project record for the given DRPID.

    Returns:
        JSON project dict or 404.
    """
    proj = get_project_by_drpid(drpid)
    if not proj:
        return {"error": "Project not found"}, 404
    return proj


@api_bp.route("/load-page", methods=["POST"])
def load_page_route() -> Any:
    """
    Fetch a URL for display in Source or Linked pane.

    Expects JSON: {url, referrer?, source_url, drpid?, from_scoreboard?}.
    Or form: url, referrer, source_url, drpid, from_scoreboard.

    Returns:
        JSON with srcdoc, status_label, h1_text, is_binary, scoreboard, etc.
    """
    if request.is_json:
        data = request.get_json() or {}
    else:
        data = {
            "url": (request.form.get("url") or "").strip(),
            "referrer": (request.form.get("referrer") or "").strip() or None,
            "source_url": (request.form.get("source_url") or "").strip(),
            "drpid": (request.form.get("drpid") or "").strip() or None,
            "from_scoreboard": (request.form.get("from_scoreboard") or "").strip() == "1",
        }
    url = _str_or_none(data.get("url")) or ""
    referrer = _str_or_none(data.get("referrer"))
    source_url = _str_or_none(data.get("source_url")) or ""
    drpid = _str_or_none(data.get("drpid"))
    from_scoreboard = data.get("from_scoreboard") is True or (data.get("from_scoreboard") == "1")
    app_root = request.url_root.rstrip("/") or request.host_url.rstrip("/")

    if not url:
        return {"error": "url required"}, 400
    if not source_url:
        return {"error": "source_url required"}, 400

    result = load_page(url, referrer, source_url, drpid, from_scoreboard, app_root)
    if result.get("error"):
        return result, 400
    return result


@api_bp.route("/load-source", methods=["POST"])
def load_source_route() -> Any:
    """
    Load the initial source URL (clears scoreboard, adds root).

    Expects JSON/form: {url, drpid?}.
    """
    if request.is_json:
        data = request.get_json() or {}
    else:
        data = {
            "url": (request.form.get("url") or "").strip(),
            "drpid": (request.form.get("drpid") or "").strip() or None,
        }
    url = _str_or_none(data.get("url")) or ""
    drpid = _str_or_none(data.get("drpid"))

    if not url:
        return {"error": "url required"}, 400
    if not is_valid_url(url):
        return {"error": "Invalid URL", "srcdoc": None, "status_label": "Error"}, 400

    clear_scoreboard()
    srcdoc, body_message, status_label, h1_text = prepare_page_content(
        url, url, drpid, for_spa=True
    )
    add_to_scoreboard(url, None, status_label)

    folder_path = None
    if drpid:
        try:
            folder_path = ensure_output_folder(int(drpid))
        except (ValueError, TypeError):
            pass
    if folder_path is None:
        folder_path = folder_path_for_drpid(drpid)

    return {
        "srcdoc": srcdoc,
        "body_message": body_message,
        "status_label": status_label,
        "h1_text": h1_text,
        "scoreboard": get_scoreboard_tree(),
        "scoreboard_urls": get_scoreboard_urls(),
        "folder_path": folder_path,
    }


@api_bp.route("/scoreboard", methods=["GET"])
def scoreboard_get() -> Any:
    """Return the current scoreboard tree."""
    return {"scoreboard": get_scoreboard_tree(), "urls": get_scoreboard_urls()}


@api_bp.route("/scoreboard/add", methods=["POST"])
def scoreboard_add() -> Any:
    """
    Add a URL to the scoreboard.

    Expects JSON/form: {url, referrer?, status_label}.
    """
    if request.is_json:
        data = request.get_json() or {}
    else:
        data = {
            "url": (request.form.get("url") or "").strip(),
            "referrer": (request.form.get("referrer") or "").strip() or None,
            "status_label": (request.form.get("status_label") or "OK").strip(),
        }
    url = _str_or_none(data.get("url")) or ""
    if not url:
        return {"error": "url required"}, 400
    referrer = _str_or_none(data.get("referrer"))
    status_label = _str_or_none(data.get("status_label")) or "OK"
    add_to_scoreboard(url, referrer, status_label)
    return {"scoreboard": get_scoreboard_tree(), "urls": get_scoreboard_urls()}


@api_bp.route("/save", methods=["POST"])
def save_route() -> Any:
    """
    Save metadata to DB and optionally generate PDFs for checked scoreboard pages.

    Expects form: drpid, folder_path, scoreboard_urls_json (JSON array),
    save_url (list of indices), metadata_*.
    Streams progress as text/plain (SAVING, DONE, ERROR).
    """
    drpid_str = (request.form.get("drpid") or "").strip()
    folder_path_str = (request.form.get("folder_path") or "").strip()
    urls_json = (request.form.get("scoreboard_urls_json") or "[]").strip()
    indices = request.form.getlist("save_url")

    # Always save metadata if drpid present.
    if drpid_str:
        try:
            drpid = int(drpid_str)
            save_metadata(
                drpid,
                folder_path_str,
                title=(request.form.get("metadata_title") or "").strip(),
                summary=(request.form.get("metadata_summary") or "").strip(),
                keywords=(request.form.get("metadata_keywords") or "").strip(),
                agency=(request.form.get("metadata_agency") or "").strip(),
                office=(request.form.get("metadata_office") or "").strip(),
                time_start=(request.form.get("metadata_time_start") or "").strip(),
                time_end=(request.form.get("metadata_time_end") or "").strip(),
                download_date=(request.form.get("metadata_download_date") or "").strip(),
            )
        except (ValueError, TypeError):
            pass

    if not folder_path_str or not indices:
        return {"done": True, "saved": 0}

    try:
        urls = json.loads(urls_json)
    except json.JSONDecodeError:
        return {"error": "Invalid scoreboard_urls_json"}, 400

    folder_path = Path(folder_path_str)
    if not folder_path.is_dir():
        return {"error": "Output folder not found"}, 400

    def stream() -> Any:
        for line in generate_save_progress(folder_path, urls, indices):
            yield line

    return Response(
        stream(),
        mimetype="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@api_bp.route("/download-file", methods=["POST"])
def download_file_route() -> Any:
    """
    Download a non-HTML URL to the project output folder.

    Expects form: url, drpid, referrer?.
    Streams progress (SAVING, PROGRESS, DONE).
    """
    url = (request.form.get("url") or "").strip()
    drpid_str = (request.form.get("drpid") or "").strip()
    referrer = (request.form.get("referrer") or "").strip() or None

    if not url or not is_valid_url(url):
        return "Invalid URL", 400
    try:
        drpid = int(drpid_str)
    except (ValueError, TypeError):
        return "Invalid DRPID", 400

    folder_path = get_result_by_drpid().get(drpid, {}).get("folder_path")
    if not folder_path:
        return "No output folder for this project", 400

    def stream() -> Any:
        for line in generate_download_progress(url, folder_path, drpid, referrer):
            yield line

    return Response(
        stream(),
        mimetype="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
