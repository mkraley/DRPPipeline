"""
Scan zip archives for member file extensions without extracting to disk.

Reads zip central directories and optionally recurses into nested archives
under time, count, and depth budgets. Intended to enrich ``extensions``
metadata only; callers should keep ``num_files`` and ``file_size`` as
on-disk totals.
"""

from __future__ import annotations

import io
import tarfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from utils.file_utils import extension_from_archive_member_name
from utils.Logger import Logger

_NESTED_ZIP_SUFFIXES = (".zip", ".jar", ".kmz")
_NESTED_TAR_SUFFIXES = (".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")


@dataclass(frozen=True)
class ZipExtensionScanBudget:
    """Limits for zip extension scanning."""

    max_depth: int = 5
    max_archives: int = 20
    max_time_sec: float = 10.0
    max_inner_archive_bytes: int = 200 * 1024 * 1024


DEFAULT_ZIP_EXTENSION_SCAN_BUDGET = ZipExtensionScanBudget()


@dataclass
class ZipExtensionScanResult:
    """Extensions discovered inside zip archives."""

    extensions: set[str] = field(default_factory=set)
    archives_scanned: int = 0
    budget_exhausted: bool = False
    warnings: list[str] = field(default_factory=list)


def scan_zip_extensions_in_folder(
    folder_path: Path,
    budget: ZipExtensionScanBudget | None = None,
) -> ZipExtensionScanResult:
    """
    Scan top-level ``.zip`` files in a folder for member extensions.

    Args:
        folder_path: Project output directory.
        budget: Scan limits; defaults to :data:`DEFAULT_ZIP_EXTENSION_SCAN_BUDGET`.

    Returns:
        Discovered extensions and any budget or parse warnings.
    """
    scan_budget = budget or DEFAULT_ZIP_EXTENSION_SCAN_BUDGET
    state = _ScanState(scan_budget)
    if not folder_path.is_dir():
        return state.to_result()

    for path in sorted(folder_path.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() != ".zip":
            continue
        if not state.time_remaining():
            state.mark_exhausted("zip extension scan time budget exceeded")
            break
        _scan_zip_path(path, state, depth=0, label=path.name)

    return state.to_result()


def _scan_zip_path(
    zip_path: Path,
    state: _ScanState,
    *,
    depth: int,
    label: str,
) -> None:
    """Open a zip file on disk and scan members."""
    if not state.can_open_archive(depth):
        return
    try:
        with zipfile.ZipFile(zip_path) as archive:
            state.note_archive_opened()
            _scan_zip_members(archive, state, depth=depth, label=label)
    except zipfile.BadZipFile:
        state.warn(f"Could not read zip for extension scan: {label}")
    except OSError as exc:
        state.warn(f"Zip extension scan failed for {label}: {exc}")


def _scan_zip_members(
    archive: zipfile.ZipFile,
    state: _ScanState,
    *,
    depth: int,
    label: str,
) -> None:
    """Record extensions from zip members and recurse into nested archives."""
    for info in archive.infolist():
        if not state.time_remaining():
            state.mark_exhausted("zip extension scan time budget exceeded")
            return
        member_name = info.filename
        if member_name.endswith("/"):
            continue

        extension = extension_from_archive_member_name(member_name)
        if extension:
            state.extensions.add(extension)

        if depth + 1 >= state.budget.max_depth:
            continue
        if not state.can_open_archive(depth + 1):
            continue

        lower_name = member_name.lower().replace("\\", "/")
        if lower_name.endswith(_NESTED_ZIP_SUFFIXES):
            _scan_nested_zip_member(archive, info, state, depth=depth, label=label)
        elif _is_tar_member(lower_name):
            _scan_nested_tar_member(archive, info, state, label=label)


def _scan_nested_zip_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    state: _ScanState,
    *,
    depth: int,
    label: str,
) -> None:
    """Inspect a zip file embedded inside another zip."""
    if info.flag_bits & 0x1:
        state.warn(f"Encrypted nested zip skipped during extension scan: {info.filename}")
        return
    if info.file_size > state.budget.max_inner_archive_bytes:
        state.warn(
            f"Nested zip too large for extension scan ({info.filename} in {label})"
        )
        return
    if not state.can_open_archive(depth + 1):
        return
    try:
        with archive.open(info, "r") as member_fp:
            payload = member_fp.read()
        with zipfile.ZipFile(io.BytesIO(payload)) as nested:
            state.note_archive_opened()
            _scan_zip_members(
                nested,
                state,
                depth=depth + 1,
                label=f"{label}:{info.filename}",
            )
    except zipfile.BadZipFile:
        state.warn(f"Could not read nested zip during extension scan: {info.filename}")
    except OSError as exc:
        state.warn(f"Nested zip extension scan failed for {info.filename}: {exc}")


def _scan_nested_tar_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    state: _ScanState,
    *,
    label: str,
) -> None:
    """Inspect a tar archive embedded inside a zip."""
    if info.flag_bits & 0x1:
        state.warn(f"Encrypted tar member skipped during extension scan: {info.filename}")
        return
    if info.file_size > state.budget.max_inner_archive_bytes:
        state.warn(
            f"Nested tar too large for extension scan ({info.filename} in {label})"
        )
        return
    try:
        with archive.open(info, "r") as member_fp:
            _scan_tar_stream(member_fp, state, label=f"{label}:{info.filename}")
    except (tarfile.TarError, OSError) as exc:
        state.warn(f"Tar extension scan failed for {info.filename}: {exc}")


def _scan_tar_stream(
    stream: BinaryIO,
    state: _ScanState,
    *,
    label: str,
) -> None:
    """Record extensions from tar members."""
    try:
        with tarfile.open(fileobj=stream, mode="r|*") as archive:
            for member in archive:
                if not state.time_remaining():
                    state.mark_exhausted("zip extension scan time budget exceeded")
                    return
                if not member.isfile():
                    continue
                extension = extension_from_archive_member_name(member.name)
                if extension:
                    state.extensions.add(extension)
    except tarfile.TarError:
        state.warn(f"Could not read tar archive during extension scan: {label}")


def _is_tar_member(member_name: str) -> bool:
    """Return True when a member path looks like a tar archive."""
    lower = member_name.lower()
    return any(lower.endswith(suffix) for suffix in _NESTED_TAR_SUFFIXES)


class _ScanState:
    """Mutable scan state shared across recursive archive walks."""

    def __init__(self, budget: ZipExtensionScanBudget) -> None:
        self.budget = budget
        self.extensions: set[str] = set()
        self.archives_scanned = 0
        self.budget_exhausted = False
        self.warnings: list[str] = []
        self._deadline = time.monotonic() + budget.max_time_sec

    def time_remaining(self) -> bool:
        """Return False when the time budget is exhausted."""
        return time.monotonic() < self._deadline and not self.budget_exhausted

    def can_open_archive(self, depth: int) -> bool:
        """Return False when depth or archive-count limits block another open."""
        if depth >= self.budget.max_depth:
            return False
        if self.archives_scanned >= self.budget.max_archives:
            self.mark_exhausted("zip extension scan archive count budget exceeded")
            return False
        return self.time_remaining()

    def note_archive_opened(self) -> None:
        """Increment the number of archives inspected."""
        self.archives_scanned += 1

    def mark_exhausted(self, message: str) -> None:
        """Record that scanning stopped early due to a budget limit."""
        self.budget_exhausted = True
        Logger.debug(message)

    def warn(self, message: str) -> None:
        """Append a recoverable scan warning."""
        self.warnings.append(message)
        Logger.debug(message)

    def to_result(self) -> ZipExtensionScanResult:
        """Build the public scan result object."""
        return ZipExtensionScanResult(
            extensions=set(self.extensions),
            archives_scanned=self.archives_scanned,
            budget_exhausted=self.budget_exhausted,
            warnings=list(self.warnings),
        )
