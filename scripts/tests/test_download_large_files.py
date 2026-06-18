"""Tests for scripts.download_large_files and export ensure helper."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestEnsureDrpidAria2Cmd(unittest.TestCase):
    def test_ensure_skips_export_when_cmd_has_lines(self) -> None:
        from scripts.export_usfs_aria2_input import ensure_drpid_aria2_cmd

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "aria2_inputs"
            out_dir.mkdir()
            cmd_path = out_dir / "DRP000042.cmd"
            cmd_path.write_text(
                '@echo off\naria2c -c -d "C:\\data" -o "big.zip" "https://example.com/x"\n',
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            with patch("scripts.export_usfs_aria2_input.export_drpid") as mock_export:
                path, count = ensure_drpid_aria2_cmd(
                    conn,
                    42,
                    output_dir=out_dir,
                    base_output_dir=Path(tmp),
                    user_agent="UA",
                    min_bytes=1,
                    missing_only=True,
                )
            mock_export.assert_not_called()
            self.assertEqual(path, cmd_path)
            self.assertEqual(count, 1)
            conn.close()

    def test_ensure_exports_when_cmd_missing(self) -> None:
        from scripts.export_usfs_aria2_input import ensure_drpid_aria2_cmd

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "aria2_inputs"
            out_dir.mkdir()
            conn = sqlite3.connect(":memory:")
            with patch("scripts.export_usfs_aria2_input.export_drpid", return_value=2) as mock_export:
                path, count = ensure_drpid_aria2_cmd(
                    conn,
                    42,
                    output_dir=out_dir,
                    base_output_dir=Path(tmp),
                    user_agent="UA",
                    min_bytes=1,
                    missing_only=True,
                )
            mock_export.assert_called_once()
            self.assertEqual(count, 2)
            self.assertEqual(path, out_dir / "DRP000042.cmd")
            conn.close()


class TestDownloadLargeFilesRunDrpid(unittest.TestCase):
    def test_run_drpid_retries_on_failure(self) -> None:
        from scripts.download_large_files import run_drpid

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "aria2_inputs"
            out_dir.mkdir()
            cmd_path = out_dir / "DRP000007.cmd"
            cmd_path.write_text(
                '@echo off\n'
                'aria2c -c -x 4 -s 4 -j 1 --file-allocation=none --max-tries=0 '
                '--retry-wait=10 --user-agent="UA" -d "C:\\data" -o "big.zip" '
                '"https://example.com/big.zip"\n',
                encoding="utf-8",
            )
            conn = sqlite3.connect(":memory:")
            mock_retry = MagicMock(return_value=(True, 2))
            with patch(
                "scripts.download_large_files.run_aria2_cmd_line_with_retries",
                mock_retry,
            ):
                code = run_drpid(
                    7,
                    conn=conn,
                    aria2_inputs_dir=out_dir,
                    base_output_dir=Path(tmp),
                    log_root=Path(tmp) / "logs",
                    summary_interval=0,
                    stop_on_error=False,
                    max_attempts=3,
                    min_bytes=1,
                    missing_only=True,
                )
            self.assertEqual(code, 0)
            mock_retry.assert_called_once()
            conn.close()


if __name__ == "__main__":
    unittest.main()
