"""
Saved DataLumos token and cookies for one terminal.

Each terminal has its own file, named with that shell's process id, so a
command in another window cannot reuse the session. The file lives in the
temp directory, outside this repo.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class TerminalDepositStore:
    """Read and write the deposit session that belongs to one terminal."""

    def __init__(
        self,
        directory: Path | None = None,
        terminal_id: int | None = None,
    ) -> None:
        """
        Args:
            directory: Folder for the session file. Defaults to the temp directory.
            terminal_id: Shell process id. Defaults to this process's parent.
        """
        self._directory = directory
        self._terminal_id = os.getppid() if terminal_id is None else terminal_id

    def load(self) -> tuple[str, dict[str, Any] | None]:
        """Return this terminal's token and cookie state, or an empty session."""
        path = self._path()
        if path is None or not path.is_file():
            return "", None
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return "", None
        if not isinstance(payload, dict):
            return "", None
        token = payload.get("token")
        state = payload.get("storageState")
        return (
            token if isinstance(token, str) else "",
            state if isinstance(state, dict) else None,
        )

    def save(self, token: str, storage_state: dict[str, Any] | None) -> None:
        """Write this terminal's token and cookies. An empty session is removed."""
        path = self._path()
        if path is None:
            return
        if not token and not storage_state:
            self.delete()
            return
        payload = {"token": token or "", "storageState": storage_state}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(payload, ensure_ascii=True)
            path.write_text(text, encoding="utf-8-sig")
        except (OSError, TypeError):
            return

    def delete(self) -> None:
        """Remove this terminal's saved session."""
        path = self._path()
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return

    def _path(self) -> Path | None:
        """Return the session file for this terminal, or None when saving is off."""
        if self._directory is None and os.environ.get("PYTEST_CURRENT_TEST"):
            return None
        folder = self._directory
        if folder is None:
            folder = Path(tempfile.gettempdir()) / "drp-datalumos-session"
        return folder / f"{self._terminal_id}.json"
