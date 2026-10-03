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
