"""
Logging configuration with singleton pattern.

Provides a centralized logger accessible via class methods.
All standard logging.Logger methods are accessible directly.

Example usage:
    from utils.Logger import Logger
    
    # Initialize logger
    Logger.initialize(log_level="INFO")
    
    # Use standard logging methods
    Logger.info("Application starting")
    Logger.debug("Debug information")
    Logger.warning("Warning message")
    Logger.error("Error occurred")
    Logger.exception("Exception details")  # Includes traceback
"""

import logging
import sys
from pathlib import Path
from typing import Optional, Union


class _DrpidFilter(logging.Filter):
    """Add drpid to the log record from Logger._current_drpid or record.extra."""

    def filter(self, record: logging.LogRecord) -> bool:
        drpid = getattr(record, "drpid", None)
        if drpid is None:
            drpid = getattr(Logger, "_current_drpid", None)
        record.drpid = f"[{drpid}] " if drpid is not None else ""
        return True


class LoggerMeta(type):
    """Metaclass to delegate all method calls to the underlying logger."""
    
    def __getattr__(cls, name: str):
        """Delegate attribute access to the underlying logger."""
        if not cls._initialized:
            raise RuntimeError("Logger has not been initialized. Call Logger.initialize() first.")
        return getattr(cls._logger, name)


class Logger(metaclass=LoggerMeta):
    """Logger class providing direct access to all logging.Logger methods."""

    _logger: Optional[logging.Logger] = None
    _initialized: bool = False
    _current_drpid: Optional[int] = None

    @classmethod
    def set_current_drpid(cls, drpid: Optional[int]) -> None:
        """Set the current project DRPID for log output. Use None to clear."""
        cls._current_drpid = drpid

    @classmethod
    def clear_current_drpid(cls) -> None:
        """Clear the current project DRPID from log output."""
        cls._current_drpid = None

    @classmethod
    def initialize(
        cls,
        log_level: str = "INFO",
        log_format: Optional[str] = None,
        log_file: Optional[Union[str, Path, bool]] = None,
    ) -> None:
        """
        Initialize the logger with specified settings.

        Logs to stdout and appends to a file (default: drp_pipeline.log in cwd).
        Format omits logger name and includes drpid when set via set_current_drpid().

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_format: Custom log format string. If None, uses default format.
                Default includes %(drpid)s (set by filter when current drpid is set).
            log_file: Path for log file. If None, uses drp_pipeline.log in current
                working directory. Pass False to disable file logging.
        """
        if cls._initialized:
            return

        if log_format is None:
            log_format = "%(asctime)s - %(levelname)s - %(drpid)s%(message)s"

        level = getattr(logging, log_level.upper(), logging.INFO)
        formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

        cls._logger = logging.getLogger("DRPPipeline")
        cls._logger.handlers.clear()
        cls._logger.filters.clear()
        cls._logger.setLevel(level)
        cls._logger.propagate = False
        cls._logger.addFilter(_DrpidFilter())

        # Stdout handler
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        cls._logger.addHandler(stream_handler)

        # File handler (append)
        if log_file is not False:
            if log_file is None:
                log_file = Path.cwd() / "drp_pipeline.log"
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            cls._logger.addHandler(file_handler)

        cls._initialized = True
    
    @classmethod
    def get_logger(cls, name: Optional[str] = None) -> logging.Logger:
        """
        Get the underlying logger instance for advanced usage.
        
        Args:
            name: Optional logger name. If None, returns the main logger.
            
        Returns:
            Logger instance
        """
        if not cls._initialized:
            raise RuntimeError("Logger has not been initialized. Call Logger.initialize() first.")
        if name is None:
            return cls._logger
        return logging.getLogger(f"DRPPipeline.{name}")
