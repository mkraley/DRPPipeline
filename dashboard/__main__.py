"""
Start the pipeline status dashboard.

Usage:
    python -m dashboard
    python -m dashboard --port 5055
    python -m dashboard --config C:\\Documents\\Code\\DRPPipeline\\config.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dashboard.server import run_server


def main() -> None:
    """Parse CLI args and run the dashboard HTTP server."""
    parser = argparse.ArgumentParser(description="DRP pipeline status dashboard")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5055,
        help="TCP port (default 5055)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.json (default: project config.json)",
    )
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, config_path=args.config)


if __name__ == "__main__":
    main()
