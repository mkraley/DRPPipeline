"""Tests for ArcFileInventory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sourcing.ArcFileInventory import MAX_DOWNLOAD_BYTES, ArcFileInventory

FIGSHARE_ARTICLE = {
    "doi": "10.15482/USDA.ADC/1",
    "files": [
        {
            "name": "small.csv",
            "size": 1000,
            "download_url": "https://ndownloader.figshare.com/files/1",
        },
        {
            "name": "huge.zip",
            "size": MAX_DOWNLOAD_BYTES + 1,
            "download_url": "https://ndownloader.figshare.com/files/2",
        },
    ],
}

DRYAD_PLACEHOLDER_ARTICLE = {
    "doi": "10.5061/dryad.abc123",
    "files": [
        {
            "name": "dryad.abc123",
            "size": 0,
            "download_url": "https://doi.org/10.5061/dryad.abc123",
        },
    ],
}


class TestArcFileInventory:
    """Tests for ARC file inventory building."""

    def test_list_files_for_figshare_article(self) -> None:
        """Hosted Figshare files are normalized with sizes."""
        inventory = ArcFileInventory()
        files = inventory.list_files_for_article(FIGSHARE_ARTICLE)
        assert len(files) == 2
        assert files[0]["source"] == "figshare"
        assert files[1]["size_bytes"] > MAX_DOWNLOAD_BYTES

    @patch.object(ArcFileInventory, "_resolve_external_files")
    def test_external_placeholder_uses_resolver(
        self,
        mock_resolve: MagicMock,
    ) -> None:
        """Single zero-byte DOI placeholder triggers external resolution."""
        mock_resolve.return_value = [
            {"name": "a.csv", "url": "https://example/a.csv", "size_bytes": 10, "source": "dryad"},
        ]
        inventory = ArcFileInventory()
        files = inventory.list_files_for_article(DRYAD_PLACEHOLDER_ARTICLE)
        assert len(files) == 1
        mock_resolve.assert_called_once()

    def test_summarize_inventory(self) -> None:
        """Summary returns counts, formatted size, extensions, and flags."""
        inventory = ArcFileInventory()
        num, size, extensions, has_large, unresolved, all_unresolved = inventory.summarize_inventory([
            {"name": "a.csv", "url": "u", "size_bytes": 100, "source": "figshare"},
            {"name": "b.zip", "url": "u", "size_bytes": MAX_DOWNLOAD_BYTES + 1, "source": "figshare"},
        ])
        assert num == 2
        assert "csv" in extensions
        assert "zip" in extensions
        assert has_large is True
        assert unresolved is False
        assert all_unresolved is False
        assert size

    def test_summarize_all_external_unresolved(self) -> None:
        """All-unresolved inventories set the all_unresolved flag."""
        inventory = ArcFileInventory()
        _num, _size, _ext, _large, unresolved, all_unresolved = inventory.summarize_inventory([
            {
                "name": "other",
                "url": "https://doi.org/10.1234/example",
                "size_bytes": 0,
                "source": "external-unresolved",
            },
        ])
        assert unresolved is True
        assert all_unresolved is True
