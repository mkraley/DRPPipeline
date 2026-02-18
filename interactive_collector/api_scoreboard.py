"""
API module for scoreboard operations.

Serves: GET /api/scoreboard, POST /api/scoreboard/add.
The scoreboard tracks visited URLs and their status (OK, 404, DL).
Tree structure supports parent-child relationships via referrer for display.
"""

from typing import Any, Dict, List, Optional

from interactive_collector.collector_state import get_scoreboard


def add_to_scoreboard(
    url: str,
    referrer: Optional[str],
    status_label: str,
    title: Optional[str] = None,
) -> None:
    """
    Append a URL to the in-memory scoreboard.

    Marks as dupe if the URL is already present. Used when loading a new page
    in the Linked pane.

    Args:
        url: The page URL.
        referrer: URL of the page that linked to this one (None for root).
        status_label: "OK", "404", etc.
        title: Optional page title for display.
    """
    board = get_scoreboard()
    existing_urls = {n["url"] for n in board}
    is_dupe = url in existing_urls
    board.append({
        "url": url,
        "referrer": referrer,
        "status_label": status_label,
        "is_dupe": is_dupe,
        "title": (title or "").strip() or None,
    })


def add_download(
    url: str,
    referrer: Optional[str],
    file_path: str,
    file_size: int,
    extension: str,
    filename: Optional[str] = None,
) -> None:
    """
    Append a downloaded-file entry (no checkbox, DL flag).

    Args:
        url: Source URL.
        referrer: Referrer URL.
        file_path: Local path.
        file_size: Size in bytes.
        extension: File extension (e.g. "pdf").
        filename: Display filename.
    """
    board = get_scoreboard()
    board.append({
        "url": url,
        "referrer": referrer,
        "status_label": "DL",
        "is_dupe": False,
        "is_download": True,
        "file_path": file_path,
        "file_size": file_size,
        "extension": extension or "",
        "filename": filename or "",
    })


def clear_scoreboard() -> None:
    """Clear the scoreboard (e.g. on initial source load)."""
    get_scoreboard().clear()


def get_scoreboard_tree() -> List[Dict[str, Any]]:
    """
    Return scoreboard as a tree (roots with children).

    One node per entry; dupes shown separately. Nodes have: url, referrer,
    status_label, is_dupe, idx, children, is_download, file_path, etc.
    """
    board = get_scoreboard()
    nodes = [
        {
            "url": n["url"],
            "referrer": n["referrer"],
            "status_label": n["status_label"],
            "is_dupe": n.get("is_dupe", False),
            "idx": i,
            "children": [],
            "is_download": n.get("is_download", False),
            "file_path": n.get("file_path"),
            "file_size": n.get("file_size", 0),
            "extension": n.get("extension", ""),
            "filename": n.get("filename", ""),
            "title": n.get("title") or None,
        }
        for i, n in enumerate(board)
    ]
    url_to_first_idx: Dict[str, int] = {}
    for i, n in enumerate(nodes):
        if n["url"] not in url_to_first_idx:
            url_to_first_idx[n["url"]] = i
    for n in nodes:
        ref = n["referrer"]
        if ref and ref in url_to_first_idx:
            nodes[url_to_first_idx[ref]]["children"].append(n)
    roots = [n for n in nodes if n["referrer"] is None or n["referrer"] not in url_to_first_idx]
    return roots


def get_scoreboard_urls() -> List[str]:
    """Return flat list of URLs in scoreboard order (for save indices)."""
    return [n["url"] for n in get_scoreboard()]


def has_url(url: str) -> bool:
    """Return True if url is already in the scoreboard."""
    return any(n["url"] == url for n in get_scoreboard())
