"""
Run the Interactive Collector web app when the package is executed with -m.

  python -m interactive_collector
"""

from interactive_collector.app import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
