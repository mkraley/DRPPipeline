"""Cross-process lock so one process edits a Google Sheet tab at a time."""

from __future__ import annotations

import msvcrt
import time
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Optional, Type

from utils.Args import Args
from utils.Logger import Logger

_LOCK_BYTES = 1
_RETRY_SECONDS = 0.5


class SheetEditLock:
    """
    Exclusive Windows file lock for one spreadsheet tab.

    The lock is held only while one project row is read and written. A second
    publish process waits, then reads the sheet after the first write finishes.
    The operating system releases the lock when this process exits.
    """

    def __init__(self, sheet_id: str, sheet_name: str) -> None:
        """
        Prepare a lock for ``sheet_id`` and ``sheet_name``.

        Args:
            sheet_id: Google spreadsheet id.
            sheet_name: Tab name inside that spreadsheet.
        """
        self._path = sheet_lock_path(sheet_id, sheet_name)
        self._handle: Optional[BinaryIO] = None
        self.waited = False

    def __enter__(self) -> SheetEditLock:
        """Acquire the lock, waiting while another process holds it."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self._path, "a+b")
        if _try_lock(self._handle):
            self.waited = False
            return self
        self.waited = True
        Logger.info(
            "Waiting for another process to finish editing the Google Sheet"
        )
        _lock_blocking(self._handle)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Release the lock."""
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        _unlock(handle)
        handle.close()


def sheet_lock_path(sheet_id: str, sheet_name: str) -> Path:
    """
    Return the lock file path beside the pipeline database.

    Args:
        sheet_id: Google spreadsheet id.
        sheet_name: Tab name inside that spreadsheet.

    Returns:
        Path to the lock file for this spreadsheet tab.
    """
    database = Path(str(Args.db_path))
    folder = database.parent if str(database.parent) else Path(".")
    return folder / f".sheet_edit_{_lock_token(sheet_id, sheet_name)}.lock"


def _lock_token(sheet_id: str, sheet_name: str) -> str:
    """Return a filesystem-safe token for this spreadsheet tab."""
    raw = f"{sheet_id}_{sheet_name}"
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in raw)
    return safe[:120] or "sheet"


def _try_lock(handle: BinaryIO) -> bool:
    """Return True when the lock is acquired without waiting."""
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, _LOCK_BYTES)
    except OSError:
        return False
    return True


def _lock_blocking(handle: BinaryIO) -> None:
    """Wait until the lock is acquired."""
    while not _try_lock(handle):
        time.sleep(_RETRY_SECONDS)


def _unlock(handle: BinaryIO) -> None:
    """Release the lock. A closed handle also releases it."""
    try:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, _LOCK_BYTES)
    except OSError:
        Logger.debug("Google Sheet edit lock was already released")
