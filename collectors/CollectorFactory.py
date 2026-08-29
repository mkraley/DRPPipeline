"""
Resolve the collector implementation for the active pipeline source.
"""

from __future__ import annotations

from typing import Type

from collectors.AdcCollector import AdcCollector
from collectors.CatalogDataCollector import CatalogDataCollector
from collectors.CmsGovCollector import CmsGovCollector
from collectors.SocrataCollector import SocrataCollector
from collectors.UsfsCollector import UsfsCollector
from utils.Args import Args

_CATALOG_SOURCES = frozenset({"ahrq", "dol"})
_SOURCE_COLLECTOR: dict[str, type] = {
    "adc": AdcCollector,
    "cdc": SocrataCollector,
    "cms": CmsGovCollector,
    "usfs": UsfsCollector,
}


def collector_class_for_source(source: str | None = None) -> type:
    """
    Return the collector class for a configured source name.

    Args:
        source: Source key from config; defaults to ``Args.source``.

    Returns:
        Collector class for the source.

    Raises:
        ValueError: When the source has no registered collector.
    """
    key = (source if source is not None else getattr(Args, "source", None) or "")
    key = str(key).strip().lower()
    if not key:
        return CatalogDataCollector
    if key in _SOURCE_COLLECTOR:
        return _SOURCE_COLLECTOR[key]
    if key in _CATALOG_SOURCES:
        return CatalogDataCollector
    raise ValueError(
        f"Unknown source {key!r} for collector. Known sources: "
        f"{', '.join(sorted(_SOURCE_COLLECTOR))}, "
        f"{', '.join(sorted(_CATALOG_SOURCES))}."
    )


def create_collector(source: str | None = None) -> object:
    """
    Instantiate the collector for the active or given source.

    Args:
        source: Optional override of ``Args.source``.

    Returns:
        Configured collector instance.
    """
    return collector_class_for_source(source)()
