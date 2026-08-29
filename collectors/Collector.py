"""
Collector entry point for DRP Pipeline.

Delegates to the implementation selected by ``Args.source`` (see
:class:`collectors.CollectorFactory`).
"""

from __future__ import annotations

from collectors.CollectorFactory import create_collector


class Collector:
    """
    Router invoked by the orchestrator as module ``collector``.

    Selects source-specific collector implementations based on ``Args.source``.
    """

    def __init__(self) -> None:
        """Create the collector implementation for the configured source."""
        self._impl = create_collector()

    def run(self, drpid: int) -> None:
        """
        Run collection for one project.

        Args:
            drpid: DRPID of the project to process.
        """
        self._impl.run(drpid)
