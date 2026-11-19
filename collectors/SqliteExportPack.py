"""
Pack a SQLite or GeoPackage export into a zip DataLumos will accept.

The archive is stored, not deflated, so a multi-gigabyte database is copied
once. Its member keeps the raw filename. The archive name is
``{layer}_gpkg.zip`` or ``{layer}_sqlite.zip``.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

_FORMAT_TOKENS = ("_geopackage", "_sqlite", "_gpkg")
_ARCHIVE_TOKEN = {".gpkg": "gpkg", ".sqlite": "sqlite"}


def sqlite_archive_name(path: Path) -> str | None:
    """Return the zip name for a SQLite or GeoPackage export.

    Args:
        path: Raw export path. The file does not need to exist.

    Returns:
        ``{layer}_gpkg.zip`` or ``{layer}_sqlite.zip``, or None for any
        other suffix.
    """
    token = _ARCHIVE_TOKEN.get(path.suffix.casefold())
    if token is None:
        return None
    return f"{_layer_name(path.stem)}_{token}.zip"


def pack_sqlite_export(path: Path) -> Path:
    """Zip a SQLite or GeoPackage export and remove the raw file.

    Args:
        path: File saved by the Hub export download.

    Returns:
        The zip when ``path`` is a SQLite or GeoPackage export. Any other
        file is returned unchanged.
    """
    archive_name = sqlite_archive_name(path)
    if archive_name is None or not path.is_file():
        return path
    dest = path.with_name(archive_name)
    if dest == path:
        return path
    if dest.is_file() and dest.stat().st_size > 0:
        path.unlink()
        return dest
    partial = dest.with_name(dest.name + ".partial")
    try:
        _write_stored_zip(partial, path)
        _replace(dest, partial)
    except OSError:
        partial.unlink(missing_ok=True)
        raise
    path.unlink()
    return dest


def _layer_name(stem: str) -> str:
    """Drop a trailing export-format token from a download stem."""
    lowered = stem.casefold()
    for token in _FORMAT_TOKENS:
        if lowered.endswith(token) and len(stem) > len(token):
            return stem[: -len(token)]
    return stem


def _write_stored_zip(archive_path: Path, member: Path) -> None:
    """Write ``member`` into a stored zip under its own filename."""
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.write(member, member.name)


def _replace(dest: Path, partial: Path) -> None:
    """Move a finished archive into place."""
    if dest.exists():
        dest.unlink()
    partial.replace(dest)
