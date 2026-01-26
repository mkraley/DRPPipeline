"""
Orchestration module for DRP Pipeline.

Coordinates module runs: resolves module from MODULES, iterates eligible projects,
and invokes run or run_one as appropriate.
"""

from orchestration.Orchestrator import Orchestrator

__all__ = ["Orchestrator"]
