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
import threading
from pathlib import Path
from typing import Dict, Optional, Union

# Human-friendly thread id: map threading.get_ident() -> 1, 2, 3, ...
_thread_id_lock = threading.Lock()
_thread_id_counter = 0
_thread_id_map: Dict[int, int] = {}


def _get_thread_id() -> int:
    """Return a stable, human-friendly thread number (1, 2, 3, ...) for the current thread."""
    ident = threading.get_ident()
    with _thread_id_lock:
        if ident not in _thread_id_map:
            global _thread_id_counter
            _thread_id_counter += 1
            _thread_id_map[ident] = _thread_id_counter
        return _thread_id_map[ident]


def _get_current_drpid() -> Optional[int]:
    """Return the current thread's drpid for log tagging (thread-safe)."""
    return getattr(Logger._thread_local, "drpid", None)


class _DrpidFilter(logging.Filter):
    """Add thread id and drpid to the log record (thread-local or record.extra)."""

    def filter(self, record: logging.LogRecord) -> bool:
        thread_id = getattr(record, "thread_id", None)
        if thread_id is None:
            thread_id = f"[T{_get_thread_id()}] "
        record.thread_id = thread_id
        drpid = getattr(record, "drpid", None)
        if drpid is None:
            drpid = _get_current_drpid()
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
    _thread_local = threading.local()

    @classmethod
    def set_current_drpid(cls, drpid: Optional[int]) -> None:
        """Set the current project DRPID for log output (thread-local). Use None to clear."""
        cls._thread_local.drpid = drpid

    @classmethod
    def clear_current_drpid(cls) -> None:
        """Clear the current project DRPID from log output for this thread."""
        cls._thread_local.drpid = None

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
        Format omits logger name and includes thread id (T1, T2, ...) and drpid when set via set_current_drpid().

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
            log_format = "%(asctime)s - %(levelname)s - %(thread_id)s%(drpid)s%(message)s"

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
