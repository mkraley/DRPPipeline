"""Tests for dashboard HTTP API (handler-level, no live socket)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from dashboard.server import make_handler
from utils.RunStatus import RunStatus


class _FakeServer:
    """Minimal server object for BaseHTTPRequestHandler."""

    def __init__(self) -> None:
        self.base_path = None


class _FakeSock:
    """Socket stand-in that captures the HTTP response bytes."""

    def __init__(self, request_bytes: bytes) -> None:
        self._request = request_bytes
        self._response = BytesIO()

    def makefile(self, mode: str, buffering: int | None = -1) -> BytesIO:
        """Return a BytesIO for request reading or response writing."""
        if "r" in mode:
            return BytesIO(self._request)
        return self._response

    def sendall(self, data: bytes) -> None:
        """Append response bytes (used by SocketIO wfile)."""
        self._response.write(data)

    def send(self, data: bytes) -> int:
        """Append response bytes and return length written."""
        self._response.write(data)
        return len(data)


class TestDashboardServer(unittest.TestCase):
    """Exercise handler routes with a fake socket pair."""

    def setUp(self) -> None:
        """Create temp config, DB, and runs dir."""
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.runs_dir = self.root / "runs"
        self.runs_dir.mkdir()
        RunStatus.reset()
        RunStatus.set_runs_dir(self.runs_dir)

        self.db_path = self.root / "epa.db"
        con = sqlite3.connect(self.db_path)
        try:
            con.execute(
                "CREATE TABLE projects ("
                "DRPID INTEGER PRIMARY KEY, status TEXT, "
                "errors TEXT, warnings TEXT)"
            )
            con.execute(
                "INSERT INTO projects (DRPID, status, errors, warnings) "
                "VALUES (1, 'sourced', '', '')"
            )
            con.commit()
        finally:
            con.close()

        self.config_path = self.root / "config.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "source": "epa",
                    "sources": {"epa": {"db_path": "epa.db"}},
                }
            ),
            encoding="utf-8-sig",
        )
        self.handler_cls = make_handler(self.config_path)

    def tearDown(self) -> None:
        """Restore RunStatus and remove temp files."""
        RunStatus.reset()
        self._tmpdir.cleanup()

    def _request(self, path: str) -> tuple[int, dict[str, str], bytes]:
        """
        Run one GET through the handler and return status, headers, body.

        Args:
            path: Request path (e.g. ``/api/stats``).
        """
        request_bytes = (
            f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode("ascii")
        )
        sock = _FakeSock(request_bytes)
        self.handler_cls(sock, ("127.0.0.1", 0), _FakeServer())
        raw = sock._response.getvalue()
        header_blob, _, body = raw.partition(b"\r\n\r\n")
        lines = header_blob.decode("latin-1").split("\r\n")
        status = int(lines[0].split(" ", 2)[1])
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        return status, headers, body

    def test_api_stats(self) -> None:
        """ /api/stats returns the config-selected DB aggregates."""
        status, headers, body = self._request("/api/stats")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("content-type", ""))
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(payload["source"], "epa")
        self.assertEqual(payload["total"], 1)
        self.assertTrue(payload["db_path"].endswith("epa.db"))

    def test_api_runs(self) -> None:
        """ /api/runs includes an active RunStatus file."""
        RunStatus.start(
            "collect",
            total=2,
            command_line=["python", "main.py", "collect"],
        )
        status, _, body = self._request("/api/runs")
        self.assertEqual(status, 200)
        payload = json.loads(body.decode("utf-8"))
        self.assertEqual(len(payload["runs"]), 1)
        self.assertEqual(payload["runs"][0]["module"], "collect")
        self.assertEqual(payload["runs"][0]["status"], "running")

    def test_index_html(self) -> None:
        """Root path serves the dashboard HTML."""
        status, headers, body = self._request("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("content-type", ""))
        html = body.decode("utf-8")
        self.assertIn("DRP Pipeline", html)
        self.assertIn("/api/runs", html)

    def test_unknown_path_404(self) -> None:
        """Unknown paths return 404."""
        status, _, _ = self._request("/nope")
        self.assertEqual(status, 404)
