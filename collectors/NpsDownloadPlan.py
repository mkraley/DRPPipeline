"""
Build NPS download destinations: product folders and public Digital Files.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sourcing.NpsReferenceRules import file_resource_id, public_digital_files
from utils.file_utils import sanitize_filename

# Project-level Digital Files sit in the NPS000xxx folder, not a subfolder.
PROJECT_FILES_FOLDER = ""
LEGACY_PROJECT_FILES_FOLDER = "_project_files"
SIDECAR_SUFFIX = "_data_table_info.csv"
PRODUCT_FOLDER_MAX_LENGTH = 80
# Win32 MAX_PATH is 260 including the trailing NUL, so usable length is 259.
MAX_WINDOWS_PATH_LENGTH = 259
_MIN_FILENAME_LENGTH = 20
_FULL_NAME_MAX_LENGTH = 500
_MAX_NAME_SUFFIX = 9999


@dataclass(frozen=True)
class NpsPlannedFile:
    """One public Digital File to download into a project or product folder."""

    url: str
    filename: str
    relative_dir: str
    size_bytes: int | None = None
    resource_id: int | None = None
    data_table_count: int = 0
    reference_id: int | None = None
    original_filename: str = ""


def product_folder_name(title: str) -> str:
    """
    Build a Windows-safe product subfolder name from the product title.

    Args:
        title: Product title (IRMA ids are not included).
    """
    return sanitize_filename(title, max_length=PRODUCT_FOLDER_MAX_LENGTH)


def unique_product_folder_name(
    title: str,
    used: set[str],
    notes: list[str] | None = None,
) -> str:
    """
    Return a product folder name that does not collide with ``used``.

    When the title is shortened to fit ``PRODUCT_FOLDER_MAX_LENGTH``, appends a
    collection-note line with the original title when ``notes`` is provided.
    """
    original = " ".join(str(title or "product").split()).strip() or "product"
    full = sanitize_filename(original, max_length=_FULL_NAME_MAX_LENGTH)
    name = _unique_folder_name(product_folder_name(original), used)
    if notes is not None and full != name:
        notes.append(f"Original product folder: {original} -> {name}")
    return name


def _unique_folder_name(base: str, used: set[str]) -> str:
    """Append ``_N`` when ``base`` already exists, keeping the name within the cap."""
    used_folded = {item.casefold() for item in used}
    if base.casefold() not in used_folded:
        used.add(base)
        return base
    for suffix in range(2, _MAX_NAME_SUFFIX + 1):
        candidate = _suffixed_filename(base, "", suffix, PRODUCT_FOLDER_MAX_LENGTH)
        if candidate.casefold() not in used_folded:
            used.add(candidate)
            return candidate
    raise RuntimeError(f"Cannot disambiguate product folder: {base}")


def planned_file_dest(folder_path: Path, relative_dir: str, filename: str) -> Path:
    """Return the on-disk path for a planned file (empty dir is project root)."""
    if relative_dir:
        return folder_path / relative_dir / filename
    return folder_path / filename


def flatten_legacy_project_files(folder_path: Path) -> None:
    """Move leftover ``_project_files`` contents to the project root and remove it."""
    legacy = folder_path / LEGACY_PROJECT_FILES_FOLDER
    if not legacy.is_dir():
        return
    for path in list(legacy.iterdir()):
        dest = folder_path / path.name
        if dest.exists():
            if path.is_file() and dest.is_file():
                path.unlink()
            continue
        path.rename(dest)
    if not any(legacy.iterdir()):
        legacy.rmdir()


def sidecar_filename(data_filename: str) -> str:
    """Return the Data Table Info CSV name next to a data file."""
    stem = sanitize_filename(data_filename).rsplit(".", 1)[0]
    return f"{stem}{SIDECAR_SUFFIX}"


def planned_files_for_profile(
    profile: dict[str, Any],
    relative_dir: str,
    holdings: list[dict[str, Any]] | None = None,
) -> list[NpsPlannedFile]:
    """
    Map public Digital Files onto download destinations.

    Args:
        profile: IRMA Profile JSON.
        relative_dir: Subfolder under the project output folder; empty is root.
        holdings: Optional GetHoldings rows for size and DataTableCount.
    """
    holdings_by_id, holdings_by_url = _index_holdings(holdings or [])
    reference_id = profile.get("referenceId")
    planned: list[NpsPlannedFile] = []
    for item in public_digital_files(profile):
        url = str(item.get("url") or "").strip()
        raw_name = str(item.get("fileName") or item.get("FileName") or "") or url.rsplit("/", 1)[-1]
        filename = sanitize_filename(raw_name)
        resource_id = file_resource_id(item)
        holding = _matching_holding(resource_id, url, holdings_by_id, holdings_by_url)
        size_bytes = _optional_int(item.get("fileSize") or item.get("FileSize"))
        table_count = 0
        if holding:
            resource_id = resource_id or _optional_int(holding.get("Id"))
            size_bytes = size_bytes or _optional_int(holding.get("FileSize"))
            table_count = int(holding.get("DataTableCount") or 0)
            url = str(holding.get("Url") or url)
            raw_name = str(holding.get("FileDescription") or raw_name)
            filename = sanitize_filename(raw_name)
        if not url or filename in {"Untitled", ""}:
            continue
        planned.append(
            NpsPlannedFile(
                url=url,
                filename=filename,
                relative_dir=relative_dir,
                size_bytes=size_bytes,
                resource_id=resource_id,
                data_table_count=table_count,
                reference_id=int(reference_id) if reference_id is not None else None,
                original_filename=raw_name.strip(),
            )
        )
    return planned


def fit_planned_files(
    folder_path: Path,
    files: list[NpsPlannedFile],
    *,
    max_path_length: int = MAX_WINDOWS_PATH_LENGTH,
) -> tuple[list[NpsPlannedFile], list[str], dict[str, str]]:
    """
    Shorten relative dirs and filenames so each destination fits Windows MAX_PATH.

    Prefers truncating the filename (preserving extension). When that is not
    enough, shortens ``relative_dir``. Returns updated planned files,
    collection-note lines for renamed originals, and a map of old→new
    relative directories.
    """
    notes: list[str] = []
    fitted: list[NpsPlannedFile] = []
    used_by_dir: dict[str, set[str]] = {}
    dir_renames: dict[str, str] = {}
    for entry in files:
        relative_dir, filename, entry_notes = _fit_one_dest(
            folder_path,
            entry.relative_dir,
            entry.filename,
            max_path_length=max_path_length,
        )
        notes.extend(entry_notes)
        if entry.relative_dir and relative_dir != entry.relative_dir:
            dir_renames[entry.relative_dir] = relative_dir
        original = (entry.original_filename or entry.filename).strip()
        full_safe = sanitize_filename(original, max_length=_FULL_NAME_MAX_LENGTH) if original else ""
        if full_safe and full_safe != filename:
            note = f"Original file: {original} -> {filename}"
            if note not in notes:
                notes.append(note)
        filename = _unique_filename(filename, used_by_dir.setdefault(relative_dir, set()))
        fitted.append(
            replace(
                entry,
                relative_dir=relative_dir,
                filename=filename,
            )
        )
    return fitted, notes, dir_renames


def drop_duplicate_planned_files(
    files: list[NpsPlannedFile],
) -> tuple[list[NpsPlannedFile], list[str]]:
    """
    Drop IRMA holdings that are the same Digital File listed more than once.

    Matches on resource id, download URL, or the same filename plus byte size.
    Same-name files with different sizes are kept for later ``_unique_filename``.
    """
    kept: list[NpsPlannedFile] = []
    notes: list[str] = []
    seen_ids: set[int] = set()
    seen_urls: set[str] = set()
    seen_name_size: set[tuple[str, int]] = set()
    for entry in files:
        reason = _duplicate_skip_note(entry, seen_ids, seen_urls, seen_name_size)
        if reason:
            notes.append(reason)
            continue
        kept.append(entry)
        if entry.resource_id is not None:
            seen_ids.add(entry.resource_id)
        if entry.url:
            seen_urls.add(entry.url.strip())
        if entry.size_bytes is not None:
            seen_name_size.add((entry.filename.casefold(), entry.size_bytes))
    return kept, notes


def apply_relative_dir_renames(
    product_profiles: list[tuple[str, dict[str, Any]]],
    dir_renames: dict[str, str],
) -> list[tuple[str, dict[str, Any]]]:
    """Remap product landing folders when path fitting shortens relative dirs."""
    if not dir_renames:
        return product_profiles
    return [(dir_renames.get(folder, folder), profile) for folder, profile in product_profiles]


def _fit_one_dest(
    folder_path: Path,
    relative_dir: str,
    filename: str,
    *,
    max_path_length: int,
) -> tuple[str, str, list[str]]:
    """Shorten one relative dir / filename pair to fit under ``max_path_length``."""
    notes: list[str] = []
    relative_dir = relative_dir.strip().strip("\\/")
    filename = sanitize_filename(filename)
    if _dest_length(folder_path, relative_dir, filename) <= max_path_length:
        return relative_dir, filename, notes

    filename_budget = _filename_budget(folder_path, relative_dir, max_path_length)
    if filename_budget < _MIN_FILENAME_LENGTH and relative_dir:
        folder_budget = max(
            8,
            max_path_length
            - len(str(folder_path))
            - 1
            - _MIN_FILENAME_LENGTH
            - 1,
        )
        shortened_dir = sanitize_filename(relative_dir, max_length=folder_budget)
        if shortened_dir != relative_dir:
            notes.append(f"Original product folder: {relative_dir} -> {shortened_dir}")
            relative_dir = shortened_dir
        filename_budget = _filename_budget(folder_path, relative_dir, max_path_length)

    shortened = sanitize_filename(
        filename,
        max_length=max(_MIN_FILENAME_LENGTH, filename_budget),
    )
    return relative_dir, shortened, notes


def _filename_budget(folder_path: Path, relative_dir: str, max_path_length: int) -> int:
    """Characters available for the basename under ``max_path_length``."""
    parent = folder_path / relative_dir if relative_dir else folder_path
    # +1 for the path separator before the filename
    return max_path_length - len(str(parent)) - 1


def _dest_length(folder_path: Path, relative_dir: str, filename: str) -> int:
    """Length of the absolute destination path string."""
    if relative_dir:
        return len(str(folder_path / relative_dir / filename))
    return len(str(folder_path / filename))


def _unique_filename(filename: str, used: set[str]) -> str:
    """Disambiguate filenames that collide after truncation."""
    used_folded = {item.casefold() for item in used}
    if filename.casefold() not in used_folded:
        used.add(filename)
        return filename
    stem, extension = filename.rsplit(".", 1) if "." in filename else (filename, "")
    limit = max(len(filename), _MIN_FILENAME_LENGTH)
    for suffix in range(2, _MAX_NAME_SUFFIX + 1):
        candidate = _suffixed_filename(stem, extension, suffix, limit)
        if candidate.casefold() not in used_folded:
            used.add(candidate)
            return candidate
    raise RuntimeError(f"Cannot disambiguate filename: {filename}")


def _suffixed_filename(stem: str, extension: str, suffix: int, limit: int) -> str:
    """Build ``stem_N.ext`` that still fits ``limit`` after truncation."""
    tail = f"_{suffix}.{extension}" if extension else f"_{suffix}"
    trimmed = stem[: max(1, limit - len(tail))]
    return sanitize_filename(trimmed + tail, max_length=limit)


def _duplicate_skip_note(
    entry: NpsPlannedFile,
    seen_ids: set[int],
    seen_urls: set[str],
    seen_name_size: set[tuple[str, int]],
) -> str:
    """Return a collection-note line when ``entry`` duplicates an earlier file."""
    if entry.resource_id is not None and entry.resource_id in seen_ids:
        return f"Skipped duplicate file: {entry.filename} (resource {entry.resource_id})"
    url = entry.url.strip()
    if url and url in seen_urls:
        return f"Skipped duplicate file: {entry.filename} ({url})"
    if entry.size_bytes is None:
        return ""
    key = (entry.filename.casefold(), entry.size_bytes)
    if key not in seen_name_size:
        return ""
    return (
        f"Skipped duplicate file: {entry.filename} "
        f"(same name and size as an earlier holding)"
    )


def _index_holdings(
    holdings: list[dict[str, Any]],
) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Index holdings by id and download URL."""
    by_id: dict[int, dict[str, Any]] = {}
    by_url: dict[str, dict[str, Any]] = {}
    for row in holdings:
        holding_id = _optional_int(row.get("Id"))
        if holding_id is not None:
            by_id[holding_id] = row
        url = str(row.get("Url") or "").strip()
        if url:
            by_url[url] = row
    return by_id, by_url


def _matching_holding(
    resource_id: int | None,
    url: str,
    by_id: dict[int, dict[str, Any]],
    by_url: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Find a holdings row for a filesAndLinks item."""
    if resource_id is not None and resource_id in by_id:
        return by_id[resource_id]
    return by_url.get(url)


def _optional_int(value: Any) -> int | None:
    """Parse an optional integer, returning None when missing or invalid."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
