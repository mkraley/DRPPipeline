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
from typing import Optional


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
    
    @classmethod
    def initialize(cls, log_level: str = "INFO", log_format: Optional[str] = None) -> None:
        """
        Initialize the logger with specified settings.
        
        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_format: Custom log format string. If None, uses default format.
        """
        if cls._initialized:
            return
        
        if log_format is None:
            log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format=log_format,
            datefmt="%Y-%m-%d %H:%M:%S",
            stream=sys.stdout
        )
        
        cls._logger = logging.getLogger("DRPPipeline")
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
