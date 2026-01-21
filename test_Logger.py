"""
Unit tests for Logger module.
"""

import logging
import sys
import unittest
from io import StringIO

from Logger import Logger


class TestLogger(unittest.TestCase):
    """Test cases for Logger class."""
    
    def setUp(self) -> None:
        """Reset Logger state before each test."""
        import logging
        # Clear any existing handlers from root logger
        logging.root.handlers = []
        Logger._logger = None
        Logger._initialized = False
    
    def test_initialize_default(self) -> None:
        """Test logger initialization with default settings."""
        Logger.initialize()
        self.assertTrue(Logger._initialized)
        self.assertIsNotNone(Logger._logger)
        # Check effective level since basicConfig affects root logger
        self.assertEqual(Logger._logger.getEffectiveLevel(), logging.INFO)
    
    def test_initialize_custom_level(self) -> None:
        """Test logger initialization with custom log level."""
        Logger.initialize(log_level="DEBUG")
        # The effective level should be DEBUG (10)
        self.assertEqual(Logger._logger.getEffectiveLevel(), logging.DEBUG)
    
    def test_initialize_error_level(self) -> None:
        """Test logger initialization with ERROR log level."""
        Logger.initialize(log_level="ERROR")
        # The effective level should be ERROR (40)
        self.assertEqual(Logger._logger.getEffectiveLevel(), logging.ERROR)
    
    def test_initialize_custom_format(self) -> None:
        """Test logger initialization with custom format."""
        Logger.initialize(log_level="INFO", log_format="%(message)s")
        self.assertTrue(Logger._initialized)
    
    def test_initialize_idempotent(self) -> None:
        """Test that initialize can be called multiple times safely."""
        Logger.initialize(log_level="DEBUG")
        first_logger = Logger._logger
        first_level = Logger._logger.getEffectiveLevel()
        
        Logger.initialize(log_level="ERROR")
        # Should still be the same logger instance
        self.assertIs(first_logger, Logger._logger)
        # Should still be DEBUG level (not changed on second call)
        self.assertEqual(Logger._logger.getEffectiveLevel(), first_level)
    
    def test_logging_methods(self) -> None:
        """Test that standard logging methods are accessible."""
        Logger.initialize(log_level="DEBUG")
        
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
        Logger.initialize()
        logger = Logger.get_logger()
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "DRPPipeline")
    
    def test_get_logger_with_name(self) -> None:
        """Test get_logger with custom name."""
        Logger.initialize()
        logger = Logger.get_logger("test_module")
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "DRPPipeline.test_module")
    
    def test_get_logger_not_initialized(self) -> None:
        """Test get_logger before initialization raises error."""
        with self.assertRaises(RuntimeError) as cm:
            Logger.get_logger()
        self.assertIn("not been initialized", str(cm.exception))


if __name__ == "__main__":
    unittest.main()

