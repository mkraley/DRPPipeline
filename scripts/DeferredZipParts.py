"""Plan stored zips that lead with folders and catalog files."""

from __future__ import annotations

import zipfile
from pathlib import Path

from collectors.PlannedFile import is_generated_sidecar


def part_suffix(index: int) -> str:
    """Return ``a``, ``b``, ... ``z``, ``aa`` for a zero-based part index."""
    number = index + 1
    letters: list[str] = []
    while number:
        number, remainder = divmod(number - 1, 26)
        letters.append(chr(ord("a") + remainder))
    return "".join(reversed(letters))


def project_directories(project_folder: Path) -> list[str]:
    """Return every directory under the project, relative and using forward slashes."""
    directories = [
        path.relative_to(project_folder).as_posix()
        for path in project_folder.rglob("*")
        if path.is_dir()
    ]
    return sorted(directories)


def catalog_files(project_folder: Path) -> list[Path]:
    """Return generated catalog and metadata files in the project."""
    files = [
        path
        for path in project_folder.rglob("*")
        if path.is_file() and is_generated_sidecar(path)
    ]
    return sorted(files, key=lambda path: path.as_posix().casefold())


def omitted_oversized_zips(paths: list[Path], max_bytes: int) -> tuple[list[Path], list[Path]]:
    """Return ``(files to pack, zip files larger than max_bytes)``."""
    packed: list[Path] = []
    omitted: list[Path] = []
    for path in paths:
        if _is_zip_over_limit(path, max_bytes):
            omitted.append(path)
            continue
        packed.append(path)
    return packed, omitted


def pack_by_max_size(paths: list[Path], max_bytes: int) -> list[list[Path]]:
    """Group files so each group stays within ``max_bytes`` when a file fits."""
    groups: list[list[Path]] = []
    current: list[Path] = []
    current_bytes = 0
    for path in paths:
        size = path.stat().st_size
        if current and current_bytes + size > max_bytes:
            groups.append(current)
            current = []
            current_bytes = 0
        current.append(path)
        current_bytes += size
    if current:
        groups.append(current)
    return groups


def plan_zip_parts(
    project_folder: Path,
    deferred: list[Path],
    max_bytes: int | None,
) -> tuple[list[tuple[list[str], list[Path]]], list[Path]]:
    """Return zip parts and zip files left out because they exceed ``max_bytes``."""
    if max_bytes is None:
        return [([], deferred)], []
    content = [path for path in deferred if not is_generated_sidecar(path)]
    packed, omitted = omitted_oversized_zips(content, max_bytes)
    groups = pack_by_max_size(packed, max_bytes) if packed else []
    parts = [(project_directories(project_folder), catalog_files(project_folder))]
    parts.extend(([], group) for group in groups)
    return parts, omitted


def _is_zip_over_limit(path: Path, max_bytes: int) -> bool:
    """Return True when ``path`` is a zip larger than ``max_bytes``."""
    return path.suffix.casefold() == ".zip" and path.stat().st_size > max_bytes


def write_stored_zip(
    project_folder: Path,
    paths: list[Path],
    dest: Path,
    directories: list[str] | None = None,
) -> None:
    """Write a stored zip using paths relative to the project folder."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    root = project_folder.resolve()
    partial = dest.with_suffix(dest.suffix + ".partial")
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_STORED) as archive:
        for relative in directories or []:
            archive.writestr(_directory_info(relative), b"")
        for path in paths:
            resolved = path.resolve()
            archive.write(resolved, resolved.relative_to(root).as_posix())
    partial.replace(dest)


def _directory_info(relative: str) -> zipfile.ZipInfo:
    """Return a zip entry for one project subdirectory."""
    name = relative.strip("/").replace("\\", "/") + "/"
    return zipfile.ZipInfo(name)
