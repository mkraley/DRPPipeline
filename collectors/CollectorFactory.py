"""
Resolve the collector implementation for the active pipeline source.
"""

from __future__ import annotations

from typing import Type

from utils.Args import Args

_CATALOG_SOURCES = frozenset({"ahrq", "dol"})
_SOURCE_KEYS = frozenset(
    {"adc", "bts", "cdc", "cms", "epa", "ferc", "nps", "ssa", "usfs"}
)


def _collector_map() -> dict[str, Type]:
    """
    Load collector classes lazily to avoid import cycles with sourcing.

    Returns:
        Map of source key to collector class.
    """
    from collectors.AdcCollector import AdcCollector
    from collectors.BtsCollector import BtsCollector
    from collectors.CmsGovCollector import CmsGovCollector
    from collectors.EpaCollector import EpaCollector
    from collectors.FercCollector import FercCollector
    from collectors.NpsCollector import NpsCollector
    from collectors.SocrataCollector import SocrataCollector
    from collectors.SsaCollector import SsaCollector
    from collectors.UsfsCollector import UsfsCollector

    return {
        "adc": AdcCollector,
        "bts": BtsCollector,
        "cdc": SocrataCollector,
        "cms": CmsGovCollector,
        "epa": EpaCollector,
        "ferc": FercCollector,
        "nps": NpsCollector,
        "ssa": SsaCollector,
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
    from collectors.CatalogDataCollector import CatalogDataCollector

    key = (source if source is not None else getattr(Args, "source", None) or "")
    key = str(key).strip().lower()
    if not key:
        return CatalogDataCollector
    collectors = _collector_map()
    if key in collectors:
        return collectors[key]
    if key in _CATALOG_SOURCES:
        return CatalogDataCollector
    raise ValueError(
        f"Unknown source {key!r} for collector. Known sources: "
        f"{', '.join(sorted(_SOURCE_KEYS))}, "
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
