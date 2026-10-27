"""
Download SSA catalog files with the shared 1 GB collector budget.

Thin alias around ``DataGovFileDownloader``.
"""

from __future__ import annotations

from collectors.DataGovFileDownloader import (
    CATALOG_PDF_NAME,
    DataGovFileDownloader,
    catalog_file_extensions,
    destination_filename,
)

SsaFileDownloader = DataGovFileDownloader

__all__ = [
    "CATALOG_PDF_NAME",
    "SsaFileDownloader",
    "catalog_file_extensions",
    "destination_filename",
]
