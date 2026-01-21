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
    from Args import Args
    
    # Initialize with optional config file
    Args.initialize()
    
    # Access configuration values as attributes
    log_level = Args.log_level  # From --log-level or config file
    config_file = Args.config_file  # From --config or config file
    
Note: Command line arguments take precedence over config file values.
Command line args use hyphens (--log-level) but are accessed with underscores (log_level).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


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
    
    _args: Optional[argparse.Namespace] = None
    _config: Dict[str, Any] = {}
    _initialized: bool = False
    
    @classmethod
    def initialize(cls, config_file: Optional[Path] = None) -> None:
        """
        Initialize configuration from command line args and config file.
        
        Args:
            config_file: Optional path to config file. If None, only command line args are used.
        """
        if cls._initialized:
            return
        
        # Parse command line arguments
        parser = cls._create_argument_parser()
        cls._args = parser.parse_args()
        
        # Load config file if provided
        config_path = config_file or cls._args.config
        if config_path and Path(config_path).exists():
            cls._load_config_file(Path(config_path))
        elif config_path and not Path(config_path).exists():
            print(f"Warning: Config file '{config_path}' not found. Using defaults and command line arguments only.",
                  file=sys.stderr)
        
        # Override config file values with command line arguments
        cls._apply_command_line_overrides()
        
        cls._initialized = True
    
    @classmethod
    def _create_argument_parser(cls) -> argparse.ArgumentParser:
        """Create and configure the argument parser."""
        parser = argparse.ArgumentParser(
            description="DRP Pipeline - Modular data collection and upload pipeline",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        
        cls._add_arguments(parser)
        
        return parser
    
    @classmethod
    def _add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """
        Add command line arguments to the parser.
        
        Args:
            parser: The argparse.ArgumentParser instance
        """
        parser.add_argument(
            "--config",
            type=Path,
            help="Path to configuration file (JSON format)"
        )
        
        parser.add_argument(
            "--log-level",
            dest="log_level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO",
            help="Set the logging level"
        )
    
    @classmethod
    def _load_config_file(cls, config_path: Path) -> None:
        """
        Load configuration from JSON file.
        
        Args:
            config_path: Path to the JSON config file
        """
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cls._config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file '{config_path}': {e}")
        except Exception as e:
            raise IOError(f"Error reading config file '{config_path}': {e}")
    
    @classmethod
    def _apply_command_line_overrides(cls) -> None:
        """Apply command line argument values to config, overriding file values."""
        # Apply all command line arguments to config dict
        # This includes defaults from argparse, which will override config file values
        # Convert Path objects to strings for config_file
        for key, value in vars(cls._args).items():
            if value is not None:
                if isinstance(value, Path):
                    cls._config[key] = str(value)
                else:
                    cls._config[key] = value
    
    @classmethod
    def get_args(cls) -> argparse.Namespace:
        """
        Get the parsed command line arguments.
        
        Returns:
            argparse.Namespace object containing all arguments
        """
        if not cls._initialized:
            raise RuntimeError("Args has not been initialized. Call Args.initialize() first.")
        return cls._args
    
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
