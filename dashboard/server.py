"""
HTTP server for the pipeline status dashboard.

Serves a static HTML page plus JSON APIs for active ``main.py`` runs and
pipeline status counts for the DB selected in ``config.json``.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dashboard.config_db import pipeline_stats
from utils.RunStatus import RunStatus

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 5055


class DashboardHandler(BaseHTTPRequestHandler):
    """Route ``/``, ``/api/runs``, and ``/api/stats``."""

    config_path: Path | None = None

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress per-request access logs (status is polled every 10s)."""
        return

    def do_GET(self) -> None:
        """Dispatch GET requests to the dashboard API or static page."""
        path = urlparse(self.path).path
        if path == "/api/runs":
            self._send_json({"runs": RunStatus.list_runs()})
            return
        if path == "/api/stats":
            self._send_json(pipeline_stats(self.config_path))
            return
        if path in ("/", "/index.html"):
            self._send_file(_STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        self.send_error(404, "Not found")

    def _send_json(self, payload: dict[str, Any]) -> None:
        """Write a JSON response with UTF-8 body."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path: Path, content_type: str) -> None:
        """Serve a static file or 404 if missing."""
        if not file_path.is_file():
            self.send_error(404, "Not found")
            return
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_handler(config_path: Path | None) -> type[DashboardHandler]:
    """
    Build a handler class bound to an optional config path.

    Args:
        config_path: Path to ``config.json``, or None for the project default.
    """

    class BoundHandler(DashboardHandler):
        """Handler with a fixed config_path for this server instance."""

    BoundHandler.config_path = config_path
    return BoundHandler


def create_server(
    host: str = _DEFAULT_HOST,
    port: int = _DEFAULT_PORT,
    config_path: Path | None = None,
) -> ThreadingHTTPServer:
    """
    Create the dashboard HTTP server (does not start serving).

    Args:
        host: Bind address (default localhost only).
        port: TCP port (default 5055).
        config_path: Optional ``config.json`` override.
    """
    handler = make_handler(config_path)
    return ThreadingHTTPServer((host, port), handler)


def run_server(
    host: str = _DEFAULT_HOST,
    port: int = _DEFAULT_PORT,
    config_path: Path | None = None,
) -> None:
    """
    Start the dashboard and block until interrupted.

    Args:
        host: Bind address.
        port: TCP port.
        config_path: Optional ``config.json`` override.
    """
    server = create_server(host=host, port=port, config_path=config_path)
    print(f"DRP pipeline dashboard: http://{host}:{port}/")
    print("Open in Cursor: Command Palette → Simple Browser: Show")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
