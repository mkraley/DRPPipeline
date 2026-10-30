"""Unit tests for utils.RunStatus."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from utils.RunStatus import RunStatus


class TestRunStatus(unittest.TestCase):
    """Cover start/update/finish, listing, and stale PID detection."""

    def setUp(self) -> None:
        """Use a temp runs directory and clear process state."""
        self._tmpdir = tempfile.TemporaryDirectory()
        self.runs_dir = Path(self._tmpdir.name)
        RunStatus.reset()
        RunStatus.set_runs_dir(self.runs_dir)

    def tearDown(self) -> None:
        """Restore defaults and remove temp files."""
        RunStatus.reset()
        self._tmpdir.cleanup()

    def test_start_writes_running_file(self) -> None:
        """start() creates {pid}.json with running status and cmdline."""
        RunStatus.start(
            "collect",
            total=10,
            command_line=["python", "main.py", "collect", "-n", "10"],
        )
        path = self.runs_dir / f"{os.getpid()}.json"
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        self.assertEqual(data["status"], "running")
        self.assertEqual(data["module"], "collect")
        self.assertEqual(data["total"], 10)
        self.assertEqual(data["completed"], 0)
        self.assertEqual(data["command_line"], "collect -n 10")
        self.assertEqual(
            data["progress_line"],
            "0/10 projects avg_per_project=n/a eta=n/a",
        )

    def test_start_skips_hidden_modules(self) -> None:
        """noop / collect_interactively / test modules are not written."""
        for module in ("noop", "collect_interactively", "my_test_module"):
            RunStatus.start(module, total=1, command_line=["main.py", module])
            self.assertIsNone(RunStatus._path)
        self.assertEqual(list(self.runs_dir.glob("*.json")), [])

    def test_list_runs_hides_noop_and_interactive(self) -> None:
        """Existing files for hidden modules are omitted from list_runs."""
        hidden = {
            "pid": 3,
            "module": "noop",
            "command_line": "noop",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "status": "completed",
            "completed": 1,
            "total": 1,
            "progress_line": "1/1 projects avg_per_project=1s eta=0:00 (12:00)",
            "errors": 0,
            "warnings": 0,
            "last_drpid": None,
        }
        (self.runs_dir / "3.json").write_text(
            json.dumps(hidden), encoding="utf-8-sig"
        )
        self.assertEqual(RunStatus.list_runs(), [])

    def test_update_progress_and_finish(self) -> None:
        """update_progress refreshes the line; finish clears active state."""
        RunStatus.start("upload", total=5, command_line=["main.py", "upload"])
        RunStatus.update_progress(
            "2/5 projects avg_per_project=1m 0.0s eta=3m 0.0s",
            display_index=2,
            total=5,
            completed=2,
            errors=1,
            warnings=3,
            last_drpid=42,
        )
        path = self.runs_dir / f"{os.getpid()}.json"
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        self.assertEqual(data["completed"], 2)
        self.assertEqual(data["errors"], 1)
        self.assertEqual(data["warnings"], 3)
        self.assertEqual(data["last_drpid"], 42)
        self.assertIn("2/5 projects", data["progress_line"])

        RunStatus.finish(completed=5, errors=1, warnings=2, status="completed")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["errors"], 1)
        self.assertEqual(data["warnings"], 2)
        self.assertIsNotNone(data["ended_at"])
        self.assertIsNone(RunStatus._path)

    def test_set_total(self) -> None:
        """set_total updates total after start."""
        RunStatus.start("collect", total=0, command_line=["main.py", "collect"])
        RunStatus.set_total(47)
        data = json.loads(
            (self.runs_dir / f"{os.getpid()}.json").read_text(encoding="utf-8-sig")
        )
        self.assertEqual(data["total"], 47)
        self.assertIn("0/47", data["progress_line"])

    def test_list_runs_orders_active_before_finished(self) -> None:
        """list_runs returns running first, then recent finished."""
        finished = {
            "pid": 1,
            "module": "publish",
            "command_line": "main.py publish",
            "started_at": "2026-10-28T10:00:00",
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "status": "completed",
            "completed": 5,
            "total": 5,
            "progress_line": "5/5 projects avg_per_project=1.0s eta=0.0s",
            "errors": 0,
            "warnings": 0,
            "last_drpid": None,
        }
        (self.runs_dir / "1.json").write_text(
            json.dumps(finished), encoding="utf-8-sig"
        )
        RunStatus.start("collect", total=3, command_line=["main.py", "collect"])
        runs = RunStatus.list_runs()
        self.assertGreaterEqual(len(runs), 2)
        self.assertEqual(runs[0]["status"], "running")
        self.assertEqual(runs[0]["module"], "collect")
        finished_rows = [r for r in runs if r["status"] == "completed"]
        self.assertEqual(finished_rows[0]["module"], "publish")

    def test_list_runs_marks_stale_when_pid_dead(self) -> None:
        """A running file for a dead PID is reported as stale."""
        dead = {
            "pid": 999999001,
            "module": "collect",
            "command_line": "main.py collect",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "ended_at": None,
            "status": "running",
            "completed": 1,
            "total": 10,
            "progress_line": "1/10 projects avg_per_project=n/a eta=n/a",
            "errors": 0,
            "warnings": 0,
            "last_drpid": None,
        }
        (self.runs_dir / "999999001.json").write_text(
            json.dumps(dead), encoding="utf-8-sig"
        )
        with patch("utils.RunStatus.pid_alive", return_value=False):
            runs = RunStatus.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "stale")

    def test_normalize_strips_spurious_collect_interactively(self) -> None:
        """Older run files with a polluted cmdline are cleaned when listed."""
        polluted = {
            "pid": 4,
            "module": "upload",
            "command_line": ".\\main.py collect_interactively upload",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "status": "completed",
            "completed": 1,
            "total": 1,
            "progress_line": "1/1 projects avg_per_project=1s eta=0:00 (12:00)",
            "errors": 0,
            "warnings": 0,
            "last_drpid": None,
        }
        (self.runs_dir / "4.json").write_text(
            json.dumps(polluted), encoding="utf-8-sig"
        )
        runs = RunStatus.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["command_line"], "upload")

    def test_list_runs_drops_old_finished(self) -> None:
        """Finished runs older than 24h are omitted."""
        old_ended = (datetime.now() - timedelta(hours=30)).isoformat(timespec="seconds")
        old = {
            "pid": 2,
            "module": "upload",
            "command_line": "main.py upload",
            "started_at": "2026-10-01T10:00:00",
            "ended_at": old_ended,
            "status": "completed",
            "completed": 1,
            "total": 1,
            "progress_line": "1/1 projects avg_per_project=1.0s eta=0.0s",
            "errors": 0,
            "warnings": 0,
            "last_drpid": None,
        }
        (self.runs_dir / "2.json").write_text(json.dumps(old), encoding="utf-8-sig")
        self.assertEqual(RunStatus.list_runs(), [])

    def test_update_without_start_is_noop(self) -> None:
        """update_progress and finish do nothing when no active run."""
        RunStatus.update_progress("1/1", display_index=1, total=1, completed=1)
        RunStatus.finish(completed=0, errors=0, warnings=0, status="completed")
        self.assertEqual(list(self.runs_dir.glob("*.json")), [])

    def test_record_project_appends_samples(self) -> None:
        """record_project stores duration and outcome for the dashboard chart."""
        RunStatus.start("collect", total=3, command_line=["main.py", "collect"])
        RunStatus.record_project(10, duration_sec=12.5, outcome="ok")
        RunStatus.record_project(11, duration_sec=3.0, outcome="warning")
        RunStatus.record_project(12, duration_sec=40.0, outcome="error")
        data = json.loads(
            (self.runs_dir / f"{os.getpid()}.json").read_text(encoding="utf-8-sig")
        )
        samples = data["project_samples"]
        self.assertEqual(len(samples), 3)
        self.assertEqual(samples[0]["drpid"], 10)
        self.assertEqual(samples[0]["duration_sec"], 12.5)
        self.assertEqual(samples[0]["outcome"], "ok")
        self.assertEqual(samples[1]["outcome"], "warning")
        self.assertEqual(samples[2]["outcome"], "error")
        self.assertTrue(samples[0]["finished_at"])

    def test_record_project_without_start_is_noop(self) -> None:
        """record_project is ignored when no active run file exists."""
        RunStatus.record_project(1, duration_sec=1.0, outcome="ok")
        self.assertEqual(list(self.runs_dir.glob("*.json")), [])
