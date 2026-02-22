"""
Downloads folder watcher for Interactive Collector.

When Copy & Open is used, the watcher monitors the user's Downloads folder.
New files (completed downloads) are moved to the active project's output folder
and added to the scoreboard. User clicks "Collection complete" to stop watching.
"""

import os
from pathlib import Path
from typing import Callable, Optional

try:
    from watchdog.events import FileSystemEventHandler
except ImportError:
    FileSystemEventHandler = object  # type: ignore

# In-progress download suffixes; skip these until the browser renames to the final file.
_INCOMPLETE_SUFFIXES = (".crdownload", ".part", ".tmp", ".temp")


def get_downloads_folder() -> Path:
    """Return the user's default Downloads folder path."""
    if os.name == "nt":
        folder = os.environ.get("USERPROFILE", "")
        if folder:
            return Path(folder) / "Downloads"
    return Path.home() / "Downloads"


def _is_complete_file(path: Path) -> bool:
    """Return True if the file is a complete download (not in-progress)."""
    if not path.is_file():
        return False
    name_lower = path.name.lower()
    return not any(name_lower.endswith(s) for s in _INCOMPLETE_SUFFIXES)


def _unique_dest_name(dest_dir: Path, base_name: str) -> Path:
    """Return a unique path in dest_dir for the given base_name."""
    dest = dest_dir / base_name
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    for i in range(1, 10000):
        candidate = dest_dir / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    return dest_dir / f"{stem}_9999{suffix}"


class _DownloadsHandler(FileSystemEventHandler):
    """Watchdog handler that moves new files to the output folder."""

    def __init__(
        self,
        output_folder: Path,
        on_file_moved: Callable[[str, Path, int], None],
    ) -> None:
        self.output_folder = output_folder
        self.on_file_moved = on_file_moved

    def _handle_file(self, src_path: Path) -> None:
        if not _is_complete_file(src_path):
            return
        try:
            size = src_path.stat().st_size
            base_name = src_path.name
            dest = _unique_dest_name(self.output_folder, base_name)
            src_path.rename(dest)
            ext = dest.suffix.lstrip(".") or ""
            self.on_file_moved(str(dest), dest, size)
        except OSError:
            pass  # File in use, permissions, etc.

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        self._handle_file(Path(event.src_path))

    def on_moved(self, event) -> None:
        if event.is_directory:
            return
        dest = getattr(event, "dest_path", None) or event.src_path
        self._handle_file(Path(dest))


_observer: Optional[object] = None
_handler: Optional[_DownloadsHandler] = None


def _get_logger():
    try:
        from utils.Logger import Logger
        return Logger
    except Exception:
        return None


def start_watching(
    drpid: int,
    output_folder: Path,
    on_new_file: Callable[[str, Path, int], None],
) -> tuple[bool, str]:
    """
    Start watching the Downloads folder. New files are moved to output_folder.

    Args:
        drpid: Active project DRPID.
        output_folder: Path to project output folder.
        on_new_file: Callback(filename, dest_path, size_bytes) when a file is moved.

    Returns:
        (success, message) - message explains failure or success.
    """
    global _observer, _handler
    try:
        from watchdog.observers import Observer
    except ImportError:
        return False, "watchdog not installed (pip install watchdog)"

    if _observer is not None:
        return False, "Watcher already active"

    downloads = get_downloads_folder()
    if not downloads.is_dir():
        return False, f"Downloads folder not found: {downloads}"

    if not output_folder.is_dir():
        output_folder.mkdir(parents=True, exist_ok=True)

    try:
        _handler = _DownloadsHandler(output_folder, on_new_file)
        _observer = Observer()
        _observer.schedule(_handler, str(downloads), recursive=False)
        _observer.start()
        log = _get_logger()
        if log:
            log.info(f"Downloads watcher started: {downloads} -> {output_folder}")
        return True, "Watching Downloads folder"
    except Exception as e:
        _observer = None
        _handler = None
        return False, str(e)


def stop_watching() -> tuple[bool, str]:
    """Stop the Downloads folder watcher."""
    global _observer, _handler
    if _observer is None:
        return True, "Watcher was not active"
    try:
        _observer.stop()
        _observer.join(timeout=5)
        log = _get_logger()
        if log:
            log.info("Downloads watcher stopped")
        return True, "Stopped watching"
    except Exception as e:
        return False, str(e)
    finally:
        _observer = None
        _handler = None


def is_watching() -> bool:
    """Return True if the watcher is currently active."""
    global _observer
    return _observer is not None
