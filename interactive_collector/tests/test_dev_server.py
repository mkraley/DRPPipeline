"""Tests for interactive_collector.dev_server."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from interactive_collector.dev_server import _env_flag, run_server


class TestDevServer(unittest.TestCase):
    """Tests for dev server startup helpers."""

    def test_env_flag_default(self) -> None:
        """Unset env vars use the provided default."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(_env_flag("FLASK_DEBUG", True))
            self.assertFalse(_env_flag("FLASK_DEBUG", False))

    def test_env_flag_false_values(self) -> None:
        """Common false strings disable the flag."""
        for value in ("0", "false", "no", "off", "FALSE"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"FLASK_DEBUG": value}, clear=True):
                    self.assertFalse(_env_flag("FLASK_DEBUG", True))

    @patch("interactive_collector.dev_server.app.run")
    def test_run_server_defaults_to_debug_and_reloader(self, mock_run: object) -> None:
        """run_server enables debug and reloader by default."""
        with patch.dict(os.environ, {}, clear=True):
            run_server()
        mock_run.assert_called_once_with(
            host="127.0.0.1",
            port=5000,
            debug=True,
            use_reloader=True,
        )

    @patch("interactive_collector.dev_server.app.run")
    def test_run_server_honors_flask_use_reloader_off(self, mock_run: object) -> None:
        """FLASK_USE_RELOADER=0 keeps debug on but disables the stat reloader."""
        with patch.dict(os.environ, {"FLASK_USE_RELOADER": "0"}, clear=True):
            run_server()
        mock_run.assert_called_once_with(
            host="127.0.0.1",
            port=5000,
            debug=True,
            use_reloader=False,
        )


if __name__ == "__main__":
    unittest.main()
