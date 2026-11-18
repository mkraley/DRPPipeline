"""
One catalog file the shared download runner can budget and store.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


_GENERATED_SIDECAR_NAMES = frozenset({
    "project_metadata.json",
    "product_metadata.json",
    "catalog_page.pdf",
    "landing_page.pdf",
    "all_metadata.pdf",
    "unsupported_exports.txt",
    "catalog_detail.pdf",
    "metadata.pdf",
    "file_index.pdf",
})


@dataclass(frozen=True)
class PlannedFile:
    """A referenced data file, not a generated sidecar."""

    relative_path: str
    source_url: str
    size_bytes: int | None = None
    # Set when HEAD/probe shows the URL is not downloadable (404, 403, …).
    access_error: str | None = None

    def destination(self, folder: Path) -> Path:
        """Return the on-disk path for this file under ``folder``."""
        return folder / PurePosixPath(self.relative_path)

    def filename(self) -> str:
        """Return the file name without its product folder."""
        return PurePosixPath(self.relative_path).name

    def relative_dir(self) -> str:
        """Return the parent folder, or an empty string at the project root."""
        parent = PurePosixPath(self.relative_path).parent
        if str(parent) == ".":
            return ""
        return str(parent)


def relative_posix(*parts: str) -> str:
    """Join path parts into a forward-slash relative path."""
    cleaned = [part.strip("/\\") for part in parts if part and part.strip("/\\")]
    return "/".join(cleaned)


def is_generated_sidecar(path: Path) -> bool:
    """
    Return True for files the collector writes locally.

    These do not count toward the 1 GiB download budget.
    """
    name = path.name.casefold()
    if name in _GENERATED_SIDECAR_NAMES:
        return True
    return name.endswith("_data_table_info.csv")


def inventory_with_deferred(
    folder: Path,
    files: list[PlannedFile],
) -> tuple[list[str], int, int]:
    """
    Return extensions, bytes, and file count, including deferred downloads.

    Files already saved count at their on-disk size. A planned file that was
    not saved, and was not refused, adds its catalog size and one file.
    """
    extensions: set[str] = set()
    total_bytes = 0
    num_files = 0
    if folder.is_dir():
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            num_files += 1
            total_bytes += path.stat().st_size
            _add_extension(extensions, path.name)
    for item in _deferred_files(folder, files):
        num_files += 1
        total_bytes += int(item.size_bytes or 0)
        _add_extension(extensions, item.filename())
    return sorted(extensions), total_bytes, num_files


def notes_with_remaining_downloads(
    notes: list[str],
    folder: Path,
    files: list[PlannedFile],
) -> list[str]:
    """Return the skip notes plus one summary of files still not downloaded."""
    from utils.collector_status import pending_download_summary_note

    kept = [line for line in notes if not line.startswith("Remaining downloads:")]
    pending = _deferred_files(folder, files)
    summary = pending_download_summary_note(
        len(pending),
        sum(int(item.size_bytes or 0) for item in pending),
        has_unknown_sizes=any(item.size_bytes is None for item in pending),
    )
    if summary:
        kept.append(summary)
    return kept


def _deferred_files(folder: Path, files: list[PlannedFile]) -> list[PlannedFile]:
    """Return planned downloads that are still absent and were not refused."""
    missing: list[PlannedFile] = []
    for item in files:
        if item.access_error:
            continue
        dest = item.destination(folder)
        if dest.is_file() and dest.stat().st_size > 0:
            continue
        missing.append(item)
    return missing


def _add_extension(extensions: set[str], filename: str) -> None:
    """Record the lowercase suffix of ``filename`` when it has one."""
    suffix = PurePosixPath(filename).suffix
    if suffix:
        extensions.add(suffix.lstrip(".").lower())
