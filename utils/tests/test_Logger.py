"""
Unit tests for Logger module.
"""

import logging
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from utils.Logger import Logger, _ColoredLevelFormatter


class TestLogger(unittest.TestCase):
    """Test cases for Logger class."""

    def setUp(self) -> None:
        """Reset Logger state before each test."""
        logging.root.handlers = []
        Logger._logger = None
        Logger._initialized = False

    def test_initialize_default(self) -> None:
        """Test logger initialization with default settings (no file in tests)."""
        Logger.initialize(log_file=False)
        self.assertTrue(Logger._initialized)
        self.assertIsNotNone(Logger._logger)
        self.assertEqual(Logger._logger.getEffectiveLevel(), logging.INFO)
        self.assertEqual(len(Logger._logger.handlers), 1)

    def test_initialize_custom_level(self) -> None:
        """Test logger initialization with custom log level."""
        Logger.initialize(log_level="DEBUG", log_file=False)
        self.assertEqual(Logger._logger.getEffectiveLevel(), logging.DEBUG)

    def test_initialize_error_level(self) -> None:
        """Test logger initialization with ERROR log level."""
        Logger.initialize(log_level="ERROR", log_file=False)
        self.assertEqual(Logger._logger.getEffectiveLevel(), logging.ERROR)

    def test_initialize_custom_format(self) -> None:
        """Test logger initialization with custom format."""
        Logger.initialize(log_level="INFO", log_format="%(message)s", log_file=False)
        self.assertTrue(Logger._initialized)

    def test_initialize_with_file(self) -> None:
        """Test logger initialization writes to file when log_file is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            Logger.initialize(log_level="INFO", log_file=str(log_path))
            Logger.info("Written to file")
            self.assertTrue(log_path.exists())
            self.assertIn("Written to file", log_path.read_text(encoding="utf-8"))
            # Close handlers so temp dir can be removed on Windows
            for h in Logger._logger.handlers:
                h.close()
            Logger._logger.handlers.clear()
            Logger._initialized = False

    def test_initialize_idempotent(self) -> None:
        """Test that initialize can be called multiple times safely."""
        Logger.initialize(log_level="DEBUG", log_file=False)
        first_logger = Logger._logger
        first_level = Logger._logger.getEffectiveLevel()

        Logger.initialize(log_level="ERROR")
        self.assertIs(first_logger, Logger._logger)
        self.assertEqual(Logger._logger.getEffectiveLevel(), first_level)

    def test_logging_methods(self) -> None:
        """Test that standard logging methods are accessible."""
        Logger.initialize(log_level="DEBUG", log_file=False)
        
        # Capture log output
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        Logger._logger.addHandler(handler)
        Logger._logger.setLevel(logging.DEBUG)
        
        Logger.debug("Debug message")
        Logger.info("Info message")
        Logger.warning("Warning message")
        Logger.error("Error message")
        
        output = log_capture.getvalue()
        self.assertIn("Debug message", output)
        self.assertIn("Info message", output)
        self.assertIn("Warning message", output)
        self.assertIn("Error message", output)
    
    def test_not_initialized_error(self) -> None:
        """Test that using logger before initialization raises error."""
        with self.assertRaises(RuntimeError) as cm:
            Logger.info("test")
        self.assertIn("not been initialized", str(cm.exception))

    def test_get_logger(self) -> None:
        """Test get_logger method."""
        Logger.initialize(log_file=False)
        logger = Logger.get_logger()
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "DRPPipeline")
    
    def test_get_logger_with_name(self) -> None:
        """Test get_logger with custom name."""
        Logger.initialize(log_file=False)
        logger = Logger.get_logger("test_module")
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "DRPPipeline.test_module")
    
    def test_get_logger_not_initialized(self) -> None:
        """Test get_logger before initialization raises error."""
        with self.assertRaises(RuntimeError) as cm:
            Logger.get_logger()
        self.assertIn("not been initialized", str(cm.exception))

    def test_initialize_with_log_color_uses_plain_formatter_when_not_tty(self) -> None:
        """When log_color=True but stdout is not a TTY, stream still uses plain formatter (no ANSI)."""
        Logger.initialize(log_level="INFO", log_color=True, log_file=False)
        stream_handler = next(h for h in Logger._logger.handlers if hasattr(h.stream, "write"))
        self.assertIsInstance(stream_handler.formatter, logging.Formatter)
        self.assertNotIsInstance(stream_handler.formatter, _ColoredLevelFormatter)

    @patch("utils.Logger.sys.stdout")
    def test_initialize_with_log_color_uses_colored_formatter_when_tty(
        self, mock_stdout: unittest.mock.MagicMock
    ) -> None:
        """When log_color=True and stdout.isatty(), stream uses ColoredLevelFormatter."""
        mock_stdout.isatty.return_value = True
        Logger.initialize(log_level="INFO", log_color=True, log_file=False)
        stream_handler = next(h for h in Logger._logger.handlers if hasattr(h.stream, "write"))
        self.assertIsInstance(stream_handler.formatter, _ColoredLevelFormatter)

    def test_colored_formatter_sets_colored_levelname(self) -> None:
        """_ColoredLevelFormatter sets record.colored_levelname and it contains the level name."""
        fmt = "%(colored_levelname)s - %(message)s"
        formatter = _ColoredLevelFormatter(fmt)
        record = logging.LogRecord("name", logging.INFO, "", 0, "hello", (), None)
        record.thread_id = ""
        record.drpid = ""
        result = formatter.format(record)
        self.assertIn("INFO", result)
        self.assertIn("hello", result)
        self.assertTrue(hasattr(record, "colored_levelname"))
        self.assertIn("INFO", record.colored_levelname)


if __name__ == "__main__":
    unittest.main()

