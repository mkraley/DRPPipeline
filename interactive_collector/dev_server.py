"""
Start the Interactive Collector Flask app with development-friendly defaults.
"""

from __future__ import annotations

import os

from interactive_collector.app import app


def _env_flag(name: str, default: bool) -> bool:
    """
    Parse a boolean environment variable.

    Args:
        name: Environment variable name.
        default: Value when the variable is unset.

    Returns:
        False when the value is 0/false/no/off (case-insensitive); True otherwise.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def run_server(host: str = "127.0.0.1", port: int = 5000) -> None:
    """
    Run the Interactive Collector web server.

    Defaults to Flask debug mode with the stat reloader and Vite SPA proxy
    (``flask run --debug``). Set ``FLASK_DEBUG=0`` to disable debug entirely.
    Set ``FLASK_USE_RELOADER=0`` to keep debug/Vite proxy but skip Python
    auto-restart (useful during long upload/publisher runs from the main page).

    Args:
        host: Bind address.
        port: Bind port.
    """
    debug = _env_flag("FLASK_DEBUG", True)
    use_reloader = _env_flag("FLASK_USE_RELOADER", debug)
    app.run(
        host=host,
        port=port,
        debug=debug,
        use_reloader=use_reloader and debug,
    )
