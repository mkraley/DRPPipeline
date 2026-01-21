"""
DRP Pipeline - Main entry point.

A modular pipeline for collecting data from various sources, e.g. government websites
and uploading to various repositories, e.g. DataLumos.
"""

import sys
from pathlib import Path

from utils.Args import Args
from utils.Logger import Logger


def setup() -> None:
    """
    Initialize the application: configuration and logging.
    
    Note: Args must be initialized before Logger since Logger configuration
    comes from Args. Args uses print() for warnings, not Logger, so this order is safe.
    """
    # Initialize configuration (handles command line args and config file)
    Args.initialize()
    
    # Initialize logger using config (Args already initialized above)
    log_level = Args.log_level
    Logger.initialize(log_level=log_level)
    
    Logger.info("DRP Pipeline starting...")
    Logger.info(f"Python version: {sys.version}")
    Logger.info(f"Working directory: {Path.cwd()}")
    
    # Log configuration info
    config_file = getattr(Args, 'config_file', None)
    if config_file:
        Logger.info(f"Using config file: {config_file}")
    Logger.info(f"Log level: {log_level}")


def main() -> None:
    """Main entry point for the DRP Pipeline application."""
    setup()
    
    # TODO: Implement pipeline logic
    Logger.info("DRP Pipeline initialized successfully")


if __name__ == "__main__":
    main()
