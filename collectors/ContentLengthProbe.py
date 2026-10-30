"""
Result of probing a download URL for Content-Length / accessibility.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContentLengthProbe:
    """
    Size and access outcome for one download URL.

    ``access_error`` is set for HTTP 401/403/404/410. Those files must not be
    treated as unknown-size (xlarge); they are project errors instead.
    """

    size_bytes: int | None = None
    access_error: str | None = None
