"""Tests for main.py Ctrl-C / entrypoint handling."""

import unittest
from unittest.mock import MagicMock, patch

import main as main_module


class TestMainEntrypoint(unittest.TestCase):
    """Ctrl-C should print a short notice and exit 130 without a traceback."""

    @patch.object(main_module, "main", side_effect=KeyboardInterrupt())
    @patch.object(main_module, "_report_keyboard_interrupt")
    def test_entrypoint_exits_130_on_keyboard_interrupt(
        self,
        mock_report: MagicMock,
        _mock_main: MagicMock,
    ) -> None:
        with self.assertRaises(SystemExit) as ctx:
            main_module.entrypoint()
        self.assertEqual(ctx.exception.code, 130)
        mock_report.assert_called_once_with()

    def test_report_keyboard_interrupt_logs_short_message(self) -> None:
        mock_logger = MagicMock()
        mock_logger._initialized = True
        with patch.object(main_module, "Logger", mock_logger):
            main_module._report_keyboard_interrupt()
        mock_logger.info.assert_called_once()
        self.assertIn("^C", mock_logger.info.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
