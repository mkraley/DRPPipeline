"""
Collectors module for DRP Pipeline.

Collectors handle the collection of data from various sources:
- Pre-process HTML (e.g., expand "read more")
- Harvest metadata
- Post-process metadata
- HTML to PDF conversion
- Download files
"""

from .CatalogDataCollector import CatalogDataCollector
from .Collector import Collector
from .CollectorFactory import collector_class_for_source, create_collector
from .SocrataCollector import SocrataCollector
from .SocrataPageProcessor import SocrataPageProcessor
from .SocrataMetadataExtractor import SocrataMetadataExtractor
from .SocrataDatasetDownloader import SocrataDatasetDownloader

__all__ = [
    'CatalogDataCollector',
    'Collector',
    'SocrataCollector',
    'SocrataPageProcessor',
    'SocrataMetadataExtractor',
    'SocrataDatasetDownloader',
    'collector_class_for_source',
    'create_collector',
]
