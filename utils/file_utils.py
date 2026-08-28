"""
Utilities for file and folder operations.

Provides functions for sanitizing filenames and creating output folders.
"""

import re
import shutil
import unicodedata
from pathlib import Path
from typing import Optional


_COMPOUND_EXTENSIONS: tuple[str, ...] = (
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tar.z",
    ".tar.lz",
)


def _split_filename_extension(name: str) -> tuple[str, str]:
    """
    Split a sanitized basename into stem and extension.

    Uses the last dotted segment when it looks like a real extension, with
    support for common compound extensions such as ``.tar.gz``.

    Args:
        name: Sanitized filename without path separators.

    Returns:
        ``(stem, extension)`` where extension includes the leading dot or is
        empty when no extension should be preserved.
    """
    lower = name.lower()
    for compound in _COMPOUND_EXTENSIONS:
        if lower.endswith(compound):
            return name[: -len(compound)], compound

    if "." not in name:
        return name, ""

    stem, ext_part = name.rsplit(".", 1)
    if not ext_part or len(ext_part) > 10:
        return name, ""
    if not all(character.isalnum() or character in "+-" for character in ext_part):
        return name, ""
    return stem, f".{ext_part}"


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """
    Sanitize a filename to be valid for Windows filesystem.
    
    Args:
        name: Original filename
        max_length: Maximum length for the sanitized name
        
    Returns:
        Sanitized filename
        
    Example:
        >>> sanitize_filename("test<file>name")
        'test_file_name'
        >>> sanitize_filename("test–file—name")
        'test-file-name'
    """
    if not name:
        return "Untitled"
    
    # Convert to string and normalize Unicode
    try:
        if isinstance(name, bytes):
            sanitized = name.decode('utf-8', errors='replace')
        else:
            sanitized = str(name)
            sanitized = unicodedata.normalize('NFKD', sanitized)
    except Exception:
        sanitized = str(name)
    
    # Replace common problematic Unicode characters
    replacements = {
        '\u2013': '-',  # en dash
        '\u2014': '-',  # em dash
        '\u2018': "'",  # left single quotation mark
        '\u2019': "'",  # right single quotation mark
        '\u201C': '"',  # left double quotation mark
        '\u201D': '"',  # right double quotation mark
        '\u2026': '...',  # ellipsis
        '\u00A0': ' ',  # non-breaking space
    }
    for old_char, new_char in replacements.items():
        sanitized = sanitized.replace(old_char, new_char)
    
    # Remove invalid Windows characters
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', sanitized)
    
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f]', '', sanitized)
    
    # Convert to ASCII
    try:
        sanitized = sanitized.encode('ascii', errors='replace').decode('ascii')
        sanitized = sanitized.replace('?', '_')
    except Exception:
        sanitized = ''.join(c if ord(c) < 128 else '_' for c in sanitized)
    
    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip('. ')
    
    # Remove multiple consecutive underscores/spaces
    sanitized = re.sub(r'[_\s]+', '_', sanitized)
    sanitized = sanitized.strip('_')
    
    # Limit length while preserving a trailing extension (e.g. .docx).
    if len(sanitized) > max_length:
        sanitized = _truncate_preserving_extension(sanitized, max_length)

    if not sanitized:
        sanitized = "Untitled"

    return sanitized


def _truncate_preserving_extension(name: str, max_length: int) -> str:
    """
    Shorten ``name`` to ``max_length`` characters without dropping the file extension.

    Args:
        name: Sanitized filename (no path separators).
        max_length: Maximum total length including extension.

    Returns:
        Truncated filename, or empty string when nothing usable remains.
    """
    if len(name) <= max_length:
        return name

    stem, extension = _split_filename_extension(name)
    if not extension:
        return name[:max_length].strip(". _")

    max_stem_len = max_length - len(extension)
    if max_stem_len < 1:
        return name[:max_length].strip(". _")

    stem = stem[:max_stem_len].strip(". _")
    if not stem:
        return extension.lstrip(".")[:max_length]
    return f"{stem}{extension}"


_SIZE_UNIT_BYTES = {
    "B": 1,
    "BYTE": 1,
    "BYTES": 1,
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
}

_SIZE_WITH_UNIT_RE = re.compile(
    r"^\s*([\d.]+)\s*(B|BYTE|BYTES|KB|MB|GB)\s*$",
    re.IGNORECASE,
)


def parse_file_size_to_bytes(value: str | int | float | None) -> int | None:
    """
    Parse a ``file_size`` field value to bytes.

    Accepts raw byte counts (``10485760``), formatted sizes from
    ``format_file_size`` (``"1.5 GB"``), DataLumos view sizes
    (``"159 bytes"``), or numeric strings.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)

    match = _SIZE_WITH_UNIT_RE.match(s)
    if match:
        num = float(match.group(1))
        unit = match.group(2).upper()
        return int(num * _SIZE_UNIT_BYTES[unit])

    try:
        return int(float(s))
    except ValueError:
        return None


def format_file_size(size_bytes: int) -> str:
    """
    Format a byte count in human-readable form (KB, MB, GB).

    Args:
        size_bytes: Size in bytes (non-negative).

    Returns:
        String like "1.2 MB", "500 KB", "3.4 GB".

    Example:
        >>> format_file_size(1536)
        '1.5 KB'
        >>> format_file_size(1_500_000)
        '1.4 MB'
    """
    if size_bytes < 0:
        size_bytes = 0
    for unit, suffix in [(1024**3, "GB"), (1024**2, "MB"), (1024, "KB")]:
        if size_bytes >= unit:
            return f"{size_bytes / unit:.1f} {suffix}"
    return f"{size_bytes} B"


def folder_extensions_and_size(folder_path: Path) -> tuple[list[str], int, int]:
    """
    Return (sorted unique extensions, total size in bytes, number of regular files).

    Only immediate children of ``folder_path`` are scanned (not recursive).

    Args:
        folder_path: Path to folder to scan

    Returns:
        Tuple of (extensions list, total bytes, file count). Extensions are lowercased, no leading dot.
    """
    exts: set[str] = set()
    total = 0
    n_files = 0
    try:
        for p in folder_path.iterdir():
            if p.is_file():
                n_files += 1
                total += p.stat().st_size
                if p.suffix:
                    exts.add(p.suffix.lstrip(".").lower())
    except OSError:
        pass
    return (sorted(exts), total, n_files)


def output_folder_prefix(sheet_name: str | None = None) -> str:
    """
    Return the prefix for project output folder names.

    Uses ``google_sheet_name`` from Args when ``sheet_name`` is omitted (e.g. ``AHRQ``).
    Falls back to ``DRP`` when Args is not initialized or the sheet name is empty.

    Args:
        sheet_name: Optional override for the sheet/tab name used as prefix.

    Returns:
        Sanitized prefix safe for Windows folder names.
    """
    if sheet_name is None:
        sheet_name = _configured_output_folder_prefix()
    name = (sheet_name or "DRP").strip()
    if not name:
        return "DRP"
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, "_", name)
    sanitized = sanitized.strip(". ")
    return sanitized or "DRP"


def _configured_output_folder_prefix() -> str:
    """Read google_sheet_name from Args, or return DRP when unavailable."""
    try:
        from utils.Args import Args

        if getattr(Args, "_initialized", False):
            configured = (getattr(Args, "google_sheet_name", None) or "DRP").strip()
            return configured or "DRP"
    except (RuntimeError, AttributeError):
        pass
    return "DRP"


def output_folder_name(drpid: int, *, prefix: str | None = None) -> str:
    """
    Return the standard output folder name for a DRPID.

    Args:
        drpid: Project DRPID.
        prefix: Optional sheet-name override; defaults to configured google_sheet_name.

    Returns:
        Folder name such as ``AHRQ000123``.

    Example:
        >>> output_folder_name(123, prefix="AHRQ")
        'AHRQ000123'
    """
    return f"{output_folder_prefix(prefix)}{drpid:06d}"


def create_output_folder(base_dir: Path, drpid: int, *, recreate: bool = True) -> Optional[Path]:
    """
    Create output folder for a DRPID.

    When ``recreate`` is True (default), an existing folder and its contents are
    removed first. When False, an existing folder is reused unchanged.

    Args:
        base_dir: Base directory for creating folders
        drpid: DRPID for the record
        recreate: When True, remove existing folder before creating

    Returns:
        Path to created folder, or None if creation failed

    Example:
        >>> from pathlib import Path
        >>> folder = create_output_folder(Path("/tmp"), 123)
        >>> folder.name  # with google_sheet_name="AHRQ"
        'AHRQ000123'
    """
    folder_name = output_folder_name(drpid)
    folder_path = base_dir / folder_name

    try:
        if folder_path.exists():
            if recreate:
                try:
                    shutil.rmtree(folder_path)
                except OSError as e:
                    from utils.Logger import Logger
                    Logger.warning(f"Could not empty output folder (in use?): {e}. Using existing folder.")
            else:
                return folder_path
        folder_path.mkdir(parents=True, exist_ok=True)
        return folder_path
    except Exception as e:
        from utils.Logger import Logger
        Logger.error(f"Failed to create output folder: {e}")
        return None
