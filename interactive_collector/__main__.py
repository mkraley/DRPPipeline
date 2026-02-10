"""
Run the Interactive Collector web app when the package is executed with -m.

  python -m interactive_collector [--db-path ...] [--config ...]

Uses Args like the rest of the pipeline; initializes Args and Logger when run standalone.
"""

import sys

# When run as python -m interactive_collector, ensure Args gets module=interactive_collector and any optional args
if len(sys.argv) >= 3 and sys.argv[1] == "-m" and sys.argv[2] == "interactive_collector":
    sys.argv = [sys.argv[0], "interactive_collector"] + sys.argv[3:]
elif len(sys.argv) < 2 or sys.argv[1] != "interactive_collector":
    sys.argv = [sys.argv[0], "interactive_collector"] + sys.argv[1:]

from utils.Args import Args
from utils.Logger import Logger

if not getattr(Args, "_initialized", False):
    Args.initialize()
    Logger.initialize(log_level=getattr(Args, "log_level", "WARNING"))

from interactive_collector.app import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
