"""Tests for dashboard.config_db."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dashboard.config_db import pipeline_stats, resolve_db_path


class TestConfigDb(unittest.TestCase):
    """Resolve DB from config source and aggregate stats."""

    def setUp(self) -> None:
        """Create a temp project dir with config and SQLite DB."""
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        self.db_path = self.root / "epa.db"
        con = sqlite3.connect(self.db_path)
        try:
            con.execute(
                "CREATE TABLE projects ("
                "DRPID INTEGER PRIMARY KEY, status TEXT, "
                "errors TEXT, warnings TEXT)"
            )
            con.executemany(
                "INSERT INTO projects (DRPID, status, errors, warnings) VALUES (?,?,?,?)",
                [
                    (1, "sourced", "", ""),
                    (2, "sourced", "", ""),
                    (3, "collected", "boom", ""),
                    (4, "uploaded", "", "soft"),
                ],
            )
            con.commit()
        finally:
            con.close()
        self.config_path = self.root / "config.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "source": "epa",
                    "sources": {
                        "epa": {"db_path": "epa.db"},
                        "adc": {"db_path": "adc.db"},
                    },
                }
            ),
            encoding="utf-8-sig",
        )

    def tearDown(self) -> None:
        """Remove temp files."""
        self._tmpdir.cleanup()

    def test_resolve_db_path_uses_active_source(self) -> None:
        """source epa maps to epa.db under the config directory."""
        source, path = resolve_db_path(self.config_path)
        self.assertEqual(source, "epa")
        self.assertEqual(path, self.db_path.resolve())

    def test_pipeline_stats_counts(self) -> None:
        """Stats reflect status histogram and error/warning counts."""
        stats = pipeline_stats(self.config_path)
        self.assertIsNone(stats["error"])
        self.assertEqual(stats["source"], "epa")
        self.assertEqual(stats["total"], 4)
        self.assertEqual(stats["with_errors"], 1)
        self.assertEqual(stats["with_warnings"], 1)
        by_status = {row["status"]: row for row in stats["by_status"]}
        self.assertEqual(by_status["sourced"]["count"], 2)
        self.assertEqual(by_status["sourced"]["label"], "sourced → collect")
        self.assertEqual(by_status["collected"]["count"], 1)
        self.assertEqual(by_status["collected"]["label"], "collected → upload")
        self.assertEqual(by_status["uploaded"]["count"], 1)
        self.assertEqual(by_status["uploaded"]["label"], "uploaded → publish")
