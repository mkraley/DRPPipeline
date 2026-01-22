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
        spreadsheet: Google Sheets URL (edit or export). If empty, uses Args.sourcing_spreadsheet_url.
        tab: Sheet gid. If empty, uses gid from spreadsheet URL.
        filter_criteria: Optional filter to restrict which rows qualify (structure TBD).
    """

    spreadsheet: str = ""
    tab: str = ""
    filter_criteria: Optional[dict[str, Any]] = None
