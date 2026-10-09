"""
Fill metadata fields from a project summary and downloaded tables.

Only values that are written in the text or in the files are returned.
Missing evidence leaves the field empty.
"""

from __future__ import annotations

from pathlib import Path

from collectors.UsfsMetadataExtractor import DATA_TYPE_GIS

from interactive_collector.metadata_inference_places import geography_from_text
from interactive_collector.metadata_inference_tables import (
    apply_preview,
    keep_value_column,
    merge_data_type,
)
from interactive_collector.metadata_inference_keywords import keywords_from_title_and_summary
from interactive_collector.metadata_inference_text import (
    data_types_from_text,
    dates_from_text,
    plain_text,
)
from interactive_collector.table_preview import iter_folder_tables

_FIELD_NAMES = ("keywords", "geographic_coverage", "data_types", "time_start", "time_end")
_GIS_SUFFIXES = {".shp", ".geojson", ".gpkg", ".kml", ".kmz"}


def infer_project_metadata(
    title: str,
    summary: str,
    folder: Path | None,
) -> tuple[dict[str, str], list[str]]:
    """
    Infer metadata fields from title, summary, and files already on disk.

    Args:
        title: Project title.
        summary: Project summary, plain text or HTML.
        folder: Directory of downloaded files. May be missing.

    Returns:
        A dict of fields that have support, and notes about unreadable files.
    """
    title_text = plain_text(title)
    summary_text = plain_text(summary)
    fields = _fields_from_text(title_text, summary_text)
    previews, notes = iter_folder_tables(folder, keep_value_column)
    for preview in previews:
        apply_preview(preview, fields)
    if _folder_has_gis(folder):
        merge_data_type(fields, DATA_TYPE_GIS)
    filled = {name: fields[name] for name in _FIELD_NAMES if fields.get(name)}
    return filled, notes


def _fields_from_text(title: str, summary: str) -> dict[str, str]:
    """Start with values stated in the title and summary."""
    text = f"{title}\n{summary}"
    start, end = dates_from_text(text)
    return {
        "time_start": start,
        "time_end": end,
        "geographic_coverage": geography_from_text(text),
        "data_types": data_types_from_text(text),
        "keywords": keywords_from_title_and_summary(title, summary),
    }


def _folder_has_gis(folder: Path | None) -> bool:
    """True when the folder contains a GIS file."""
    if folder is None or not folder.is_dir():
        return False
    return any(path.suffix.lower() in _GIS_SUFFIXES for path in folder.rglob("*") if path.is_file())
