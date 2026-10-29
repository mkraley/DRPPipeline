"""Tests for Cursor terminal discovery and merge."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dashboard.cursor_terminals import (
    cursor_terminals_dir,
    list_pipeline_terminals,
    merge_runs_with_terminals,
)


class TestCursorTerminals(unittest.TestCase):
    """Parse terminal files and merge with run-status records."""

    def setUp(self) -> None:
        """Create a temp terminals directory with sample files."""
        self._tmpdir = tempfile.TemporaryDirectory()
        self.term_dir = Path(self._tmpdir.name)
        (self.term_dir / "4.txt").write_text(
            "---\n"
            "pid: 17368\n"
            "cwd: |\n"
            "  C:\\Documents\\Code\\DRPPipeline\n"
            "active_command: python .\\main.py upload\n"
            "---\n"
            "log line\n",
            encoding="utf-8-sig",
        )
        (self.term_dir / "5.txt").write_text(
            "---\n"
            "pid: 28268\n"
            "last_command: python .\\main.py resume_upload\n"
            "last_exit_code: 0\n"
            "---\n"
            "done\n",
            encoding="utf-8-sig",
        )
        (self.term_dir / "3.txt").write_text(
            "---\n"
            "pid: 13824\n"
            "active_command: python -m dashboard\n"
            "---\n",
            encoding="utf-8-sig",
        )

    def tearDown(self) -> None:
        """Remove temp files."""
        self._tmpdir.cleanup()

    def test_list_pipeline_terminals_skips_dashboard(self) -> None:
        """Only main.py batch terminals are returned."""
        terms = list_pipeline_terminals(self.term_dir)
        pids = {row["pid"] for row in terms}
        self.assertEqual(pids, {17368, 28268})
        active = {row["pid"]: row["active"] for row in terms}
        self.assertTrue(active[17368])
        self.assertFalse(active[28268])

    def test_merge_attaches_terminal_pid_and_command(self) -> None:
        """Merge prefers Cursor terminal PIDs on the cards."""
        runs = [
            {
                "pid": 26340,
                "terminal_pid": 17368,
                "module": "upload",
                "command_line": "upload",
                "started_at": "2026-10-29T13:26:31",
                "ended_at": None,
                "status": "running",
                "completed": 2,
                "total": 10,
                "progress_line": "2/10 projects",
                "errors": 0,
                "warnings": 0,
            },
            {
                "pid": 27692,
                "terminal_pid": None,
                "module": "resume_upload",
                "command_line": "resume_upload",
                "started_at": "2026-10-29T13:28:17",
                "ended_at": "2026-10-29T14:23:51",
                "status": "completed",
                "completed": 18,
                "total": 18,
                "progress_line": "18/18 projects",
                "errors": 0,
                "warnings": 0,
            },
        ]
        terms = list_pipeline_terminals(self.term_dir)
        merged = merge_runs_with_terminals(runs, terms)
        by_term = {row["terminal_pid"]: row for row in merged}
        self.assertIn(17368, by_term)
        self.assertEqual(by_term[17368]["status"], "running")
        self.assertEqual(by_term[17368]["command_line"], "upload")
        self.assertIn(28268, by_term)
        self.assertEqual(by_term[28268]["module"], "resume_upload")
        self.assertEqual(by_term[28268]["status"], "completed")
        self.assertEqual(by_term[28268]["progress_line"], "18/18 projects")

    def test_cursor_terminals_dir_slug(self) -> None:
        """Project path maps to the Cursor projects slug layout when present."""
        path = cursor_terminals_dir()
        if path is not None:
            self.assertEqual(path.name, "terminals")
            self.assertIn("c-Documents-Code-DRPPipeline", path.parts)
