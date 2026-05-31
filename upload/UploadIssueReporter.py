"""Persist upload warnings and errors to Storage for the active DRPID."""

from __future__ import annotations

from utils.Errors import record_error, record_warning


class UploadIssueReporter:
    """Route upload-time warnings and errors to the project record."""

    def __init__(self, drpid: int) -> None:
        self._drpid = drpid

    @property
    def drpid(self) -> int:
        return self._drpid

    def warn(self, msg: str) -> None:
        """Log and append a non-fatal warning to the project ``warnings`` field."""
        record_warning(self._drpid, msg)

    def error(self, msg: str) -> None:
        """Log and append a fatal error to the project ``errors`` field."""
        record_error(self._drpid, msg)
