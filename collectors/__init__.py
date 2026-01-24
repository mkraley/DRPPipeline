"""
Collectors module for DRP Pipeline.

Collectors handle the collection of data from various sources:
- Pre-process HTML (e.g., expand "read more")
- Harvest metadata
- Post-process metadata
- HTML to PDF conversion
- Download files
"""

from .SocrataCollector import SocrataCollector
from .SocrataPageProcessor import SocrataPageProcessor
from .SocrataMetadataExtractor import SocrataMetadataExtractor
from .SocrataDatasetDownloader import SocrataDatasetDownloader

__all__ = ['SocrataCollector', 'SocrataPageProcessor', 'SocrataMetadataExtractor', 'SocrataDatasetDownloader']
