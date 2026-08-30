"""
Resolve the sourcing implementation for the active pipeline source.
"""

from __future__ import annotations

from typing import Type

from sourcing.AdcSourcing import AdcSourcing
from sourcing.BtsSourcing import BtsSourcing
from sourcing.SourcingBase import SourcingBase
from sourcing.SpreadsheetSourcing import SpreadsheetSourcing
from utils.Args import Args

_ADC_SOURCE = "adc"
_BTS_SOURCE = "bts"
_SPREADSHEET_SOURCES = frozenset({"ahrq", "cdc", "cms", "dol", "usfs"})


def sourcing_class_for_source(source: str | None = None) -> Type[SourcingBase]:
    """
    Return the sourcing class for a configured source name.

    Args:
        source: Source key from config; defaults to ``Args.source``.

    Returns:
        ``AdcSourcing`` for ADC; ``SpreadsheetSourcing`` for sheet-based sources.
    """
    key = (source if source is not None else getattr(Args, "source", None) or "")
    key = str(key).strip().lower()
    if key == _ADC_SOURCE:
        return AdcSourcing
    if key == _BTS_SOURCE:
        return BtsSourcing
    if key in _SPREADSHEET_SOURCES or not key:
        return SpreadsheetSourcing
    raise ValueError(
        f"Unknown source {key!r}. Known spreadsheet sources: "
        f"{', '.join(sorted(_SPREADSHEET_SOURCES))}; "
        f"API sources: {_ADC_SOURCE!r}, {_BTS_SOURCE!r}."
    )


def create_sourcing(source: str | None = None) -> SourcingBase:
    """
    Instantiate the sourcing module for the active or given source.

    Args:
        source: Optional override of ``Args.source``.

    Returns:
        Configured sourcing implementation.
    """
    return sourcing_class_for_source(source)()
