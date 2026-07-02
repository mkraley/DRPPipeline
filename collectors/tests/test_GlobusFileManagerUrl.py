"""Tests for GlobusFileManagerUrl parsing."""

from __future__ import annotations

from collectors.GlobusFileManagerUrl import GlobusFileManagerUrl


class TestGlobusFileManagerUrl:
    """Tests for Globus File Manager URL parsing."""

    def test_from_url_parses_origin_id_and_path(self) -> None:
        """Query parameters decode to endpoint UUID and POSIX path."""
        url = (
            "https://app.globus.org/file-manager?"
            "origin_id=1e5031de-bb2d-4217-8f35-eda23529faa4&"
            "origin_path=%2Fnode29313%2F"
        )
        parsed = GlobusFileManagerUrl.from_url(url)
        assert parsed is not None
        assert parsed.origin_id == "1e5031de-bb2d-4217-8f35-eda23529faa4"
        assert parsed.origin_path == "/node29313/"

    def test_from_status_notes_external_data_url_prefix(self) -> None:
        """status_notes with External data URL prefix is parsed."""
        notes = (
            "External data URL: https://app.globus.org/file-manager?"
            "origin_id=abc&origin_path=%2Fdata%2F"
        )
        parsed = GlobusFileManagerUrl.from_status_notes(notes)
        assert parsed is not None
        assert parsed.origin_id == "abc"
        assert parsed.origin_path == "/data/"

    def test_from_status_notes_non_globus_returns_none(self) -> None:
        """Non-Globus external URLs return None."""
        notes = "External data URL: https://www.lcacommons.gov/"
        assert GlobusFileManagerUrl.from_status_notes(notes) is None
