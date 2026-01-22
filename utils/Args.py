"""
Command line arguments and configuration with singleton pattern.

Provides a centralized configuration accessible via direct attribute access.
Supports both command line arguments and config file values.

Config File Format:
    JSON format with simple key-value pairs.
    
    Example config.json:
    {
        "log_level": "DEBUG",
        "config_file": "config.json"
    }

Example usage:
    from utils.Args import Args
    
    # Initialize with optional config file
    Args.initialize()
    
    # Access configuration values as attributes
    log_level = Args.log_level  # From --log-level, config file, or defaults
    config_file = Args.config_file  # From --config or config file

Note: Priority order (highest to lowest):
    1. Command line arguments (from Typer)
    2. Config file values
    3. Default values (from defaults dict)
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import typer


class ArgsMeta(type):
    """Metaclass to provide direct attribute access to config values."""
    
    def __getattr__(cls, name: str):
        """Provide attribute access to config values."""
        if not cls._initialized:
            raise RuntimeError("Args has not been initialized. Call Args.initialize() first.")
        
        # Check config dict (command line overrides already applied)
        if name in cls._config:
            return cls._config[name]
        
        raise AttributeError(f"Config item '{name}' not found")


class Args(metaclass=ArgsMeta):
    """Args class providing direct attribute access to configuration."""
    
    # Default values (lowest priority)
    _defaults: Dict[str, Any] = {
        "log_level": "INFO",
        "sourcing_spreadsheet_url": (
            "https://docs.google.com/spreadsheets/d/1OYLn6NBWStOgPUTJfYpU0y0g4uY7roIPP4qC2YztgWY/edit?gid=101637367#gid=101637367"
        ),
        "sourcing_url_column": "URL",
        "sourcing_filter_empty_columns": [
            "Claimed (add your name)",
            "Download Location",
        ],
    }
    
    _config: Dict[str, Any] = {}
    _initialized: bool = False
    _app: Optional[typer.Typer] = None
    _parsed_args: Dict[str, Any] = {}

    @classmethod
    def initialize(cls, config_file: Optional[Path] = None) -> None:
        """
        Initialize configuration from defaults, config file, and command line args.
        
        Priority order (highest to lowest):
            1. Command line arguments
            2. Config file values
            3. Default values
        
        Args:
            config_file: Optional path to config file. If None, uses --config from command line or no config file.
        """
        if cls._initialized:
            return
        
        # Start with defaults (lowest priority)
        cls._config = dict(cls._defaults)
        
        # Parse command line arguments first to get config file path if not provided
        parsed_args = cls._parse_command_line()
        
        # Load config file if provided (middle priority - overrides defaults)
        config_path = config_file or parsed_args.get("config")
        if config_path:
            if not isinstance(config_path, Path):
                config_path = Path(config_path)
            if config_path.exists():
                cls._load_config_file(config_path)
            else:
                # Warn if config file specified but not found (from parameter or command line)
                print(f"Warning: Config file '{config_path}' not found. Using defaults and command line arguments only.",
                      file=sys.stderr)
        
        # Apply command line arguments (highest priority - overrides config file and defaults)
        cls._apply_command_line_args(parsed_args)
        
        cls._initialized = True

    @classmethod
    def _parse_command_line(cls) -> Dict[str, Any]:
        """
        Parse command line arguments using Typer.
        
        Returns:
            Dictionary of parsed command line arguments
        """
        # Store parsed values in a dict that can be accessed from the callback
        parsed_values: Dict[str, Any] = {}
        
        def callback(
            ctx: typer.Context,
            config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to configuration file (JSON format)"),
            log_level: Optional[str] = typer.Option(None, "--log-level", "-l", help="Set the logging level", 
                                                     case_sensitive=False)
        ) -> None:
            """Callback to capture Typer parsed values."""
            if config is not None:
                parsed_values["config"] = config
            if log_level is not None:
                # Normalize to uppercase
                parsed_values["log_level"] = log_level.upper()
        
        # Create Typer app with callback
        app = typer.Typer(help="DRP Pipeline - Modular data collection and upload pipeline")
        app.callback(invoke_without_command=True)(callback)
        
        # Parse sys.argv, but handle unittest case where we might need to skip certain args
        # Typer will handle parsing, but we need to catch SystemExit that Typer might raise
        try:
            app(sys.argv[1:], standalone_mode=False)
        except SystemExit:
            # Typer may raise SystemExit for help/errors, but we want to continue in unittest
            pass
        
        return parsed_values

    @classmethod
    def _load_config_file(cls, config_path: Path) -> None:
        """
        Load configuration from JSON file and merge into config.
        
        Args:
            config_path: Path to the JSON config file
        """
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_file_data = json.load(f)
                # Merge config file data into existing config (overriding defaults)
                cls._config.update(config_file_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file '{config_path}': {e}")
        except Exception as e:
            raise IOError(f"Error reading config file '{config_path}': {e}")

    @classmethod
    def _apply_command_line_args(cls, parsed_args: Dict[str, Any]) -> None:
        """
        Apply command line argument values to config, overriding file values and defaults.
        
        Args:
            parsed_args: Dictionary of parsed command line arguments from Typer
        """
        # Store parsed args for get_args() method
        cls._parsed_args = parsed_args
      
        # Merge command line args into config (overriding config file and defaults)
        # Only include values that were actually provided (not None)
        for key, value in parsed_args.items():
            if value is not None:
                cls._config[key] = value

    @classmethod
    def get_args(cls) -> Dict[str, Any]:
        """
        Get the parsed command line arguments.
        
        Returns:
            Dictionary containing all command line arguments that were provided
        """
        if not cls._initialized:
            raise RuntimeError("Args has not been initialized. Call Args.initialize() first.")
        return cls._parsed_args.copy()

    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """
        Get the full configuration dictionary.
        
        Returns:
            Dictionary containing all configuration values
        """
        if not cls._initialized:
            raise RuntimeError("Args has not been initialized. Call Args.initialize() first.")
        return cls._config.copy()
