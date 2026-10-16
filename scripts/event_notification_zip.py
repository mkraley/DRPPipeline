"""Zip a finished year of event-notification PDFs."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path


def should_zip_year(months: set[int], failed: int) -> bool:
    """A year is ready to zip when every month was requested and none failed."""
    return failed == 0 and months == set(range(1, 13))


def year_archive_path(dest: Path, year: int) -> Path:
    """Return ``dest\\{year}.zip``."""
    return dest / f"{year}.zip"


def year_is_archived(dest: Path, year: int) -> bool:
    """Return True when the year zip exists and the loose year folder does not."""
    return year_archive_path(dest, year).is_file() and not (dest / str(year)).exists()


def zip_year_folder(dest: Path, year: int) -> Path | None:
    """
    Zip ``dest\\{year}\\{mm}\\`` into ``dest\\{year}.zip``.

    Month folders are at the top of the archive. The loose year folder is
    removed after the zip is in place. Returns None when there is nothing to zip.
    """
    year_dir = dest / str(year)
    pdfs = sorted(year_dir.glob("*/*.pdf")) if year_dir.is_dir() else []
    if not pdfs:
        return None
    target = year_archive_path(dest, year)
    partial = dest / f"{year}.zip.partial"
    _write_year_zip(partial, pdfs)
    partial.replace(target)
    shutil.rmtree(year_dir)
    return target


def _write_year_zip(path: Path, pdfs: list[Path]) -> None:
    """Write month folders and their PDFs into ``path``."""
    months = sorted({pdf.parent.name for pdf in pdfs})
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for month in months:
            archive.writestr(f"{month}/", b"")
        for pdf in pdfs:
            archive.write(pdf, f"{pdf.parent.name}/{pdf.name}")
