"""
Source configuration for Sourcing module.

Parameterizes where candidate URLs come from, e.g. spreadsheet/tab and filter criteria.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class SourceConfig:
    """
    Configuration for a single source of candidate URLs.

    Attributes:
        spreadsheet: Path or ID of the source spreadsheet (e.g. DRP Data_Inventories).
        tab: Sheet/tab name within the spreadsheet.
        filter_criteria: Optional filter to restrict which rows qualify (structure TBD).
    """

    spreadsheet: str
    tab: str
    filter_criteria: Optional[dict[str, Any]] = None
