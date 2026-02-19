"""
Unit tests for the Interactive Collector JSON API.
"""

import json
import unittest
from unittest.mock import patch

from interactive_collector.app import app
from interactive_collector.api_scoreboard import clear_scoreboard


class TestApiProjects(unittest.TestCase):
    """Tests for /api/projects/* endpoints."""

    def setUp(self) -> None:
        """Use test client for each test."""
        self.client = app.test_client()

    def test_projects_first_returns_json_or_404(self) -> None:
        """GET /api/projects/first returns project or 404."""
        with patch("interactive_collector.api.get_first_eligible", return_value=None):
            resp = self.client.get("/api/projects/first")
            self.assertEqual(resp.status_code, 404)
            data = json.loads(resp.data)
            self.assertIn("error", data)

    def test_projects_next_requires_current_drpid(self) -> None:
        """GET /api/projects/next without current_drpid returns 400."""
        resp = self.client.get("/api/projects/next")
        self.assertEqual(resp.status_code, 400)

    def test_projects_get_returns_404_for_missing(self) -> None:
        """GET /api/projects/999 returns 404 when not found."""
        with patch("interactive_collector.api.get_project_by_drpid", return_value=None):
            resp = self.client.get("/api/projects/999")
            self.assertEqual(resp.status_code, 404)


class TestApiLoadSource(unittest.TestCase):
    """Tests for /api/load-source."""

    def setUp(self) -> None:
        self.client = app.test_client()
        clear_scoreboard()

    def test_load_source_requires_url(self) -> None:
        """POST /api/load-source without url returns 400."""
        resp = self.client.post(
            "/api/load-source",
            json={},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_load_source_rejects_invalid_url(self) -> None:
        """POST /api/load-source with invalid URL returns 400."""
        resp = self.client.post(
            "/api/load-source",
            json={"url": "not-a-url"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


class TestApiProxy(unittest.TestCase):
    """Tests for /api/proxy (resource proxy for iframe CSS/JS/images)."""

    def setUp(self) -> None:
        self.client = app.test_client()

    def test_proxy_requires_valid_url(self) -> None:
        """GET /api/proxy without url or with invalid url returns 400."""
        resp = self.client.get("/api/proxy")
        self.assertEqual(resp.status_code, 400)
        resp = self.client.get("/api/proxy?url=not-a-url")
        self.assertEqual(resp.status_code, 400)


class TestApiScoreboard(unittest.TestCase):
    """Tests for /api/scoreboard."""

    def setUp(self) -> None:
        self.client = app.test_client()
        clear_scoreboard()

    def test_scoreboard_get_returns_empty(self) -> None:
        """GET /api/scoreboard returns scoreboard and urls."""
        resp = self.client.get("/api/scoreboard")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("scoreboard", data)
        self.assertIn("urls", data)
        self.assertEqual(data["scoreboard"], [])
        self.assertEqual(data["urls"], [])


class TestApiPipeline(unittest.TestCase):
    """Tests for /api/pipeline/* endpoints."""

    def setUp(self) -> None:
        self.client = app.test_client()

    def test_pipeline_modules_returns_list(self) -> None:
        """GET /api/pipeline/modules returns module names in Orchestrator order, no noop."""
        resp = self.client.get("/api/pipeline/modules")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("modules", data)
        mods = data["modules"]
        self.assertIsInstance(mods, list)
        self.assertIn("sourcing", mods)
        self.assertIn("interactive_collector", mods)
        self.assertNotIn("noop", mods)

    def test_pipeline_run_requires_module(self) -> None:
        """POST /api/pipeline/run without module returns 400."""
        resp = self.client.post(
            "/api/pipeline/run",
            json={},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertIn("error", data)

    def test_pipeline_run_rejects_unknown_module(self) -> None:
        """POST /api/pipeline/run with unknown module returns 400."""
        resp = self.client.post(
            "/api/pipeline/run",
            json={"module": "unknown_module"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertIn("error", data)

    def test_pipeline_run_interactive_collector_returns_400(self) -> None:
        """POST /api/pipeline/run with interactive_collector returns 400 (use button instead)."""
        resp = self.client.post(
            "/api/pipeline/run",
            json={"module": "interactive_collector"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.data)
        self.assertIn("error", data)

    def test_pipeline_stop_returns_ok(self) -> None:
        """POST /api/pipeline/stop returns 200 and ok: true."""
        resp = self.client.post("/api/pipeline/stop")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data.get("ok"), True)

    def test_pipeline_run_noop_streams_output(self) -> None:
        """POST /api/pipeline/run with noop streams log output."""
        proc = unittest.mock.MagicMock()
        proc.stdout = iter(
            ["2025-01-01 12:00:00 - INFO - DRP Pipeline starting...\n", "Done\n"]
        )
        proc.poll.return_value = 0
        proc.wait.return_value = 0
        with patch(
            "interactive_collector.api_pipeline.subprocess.Popen",
            return_value=proc,
        ) as mock_popen:
            resp = self.client.post(
                "/api/pipeline/run",
                json={"module": "noop"},
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.data.decode("utf-8")
            self.assertIn("DRP Pipeline", body)
            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]
            self.assertIn("noop", call_args)
