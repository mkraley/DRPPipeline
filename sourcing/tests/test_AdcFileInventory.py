"""Tests for AdcFileInventory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sourcing.AdcFileInventory import MAX_DOWNLOAD_BYTES, AdcFileInventory

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


class TestAdcFileInventory:
    """Tests for ADC file inventory building."""

    def test_list_files_for_figshare_article(self) -> None:
        """Hosted Figshare files are normalized with sizes."""
        inventory = AdcFileInventory()
        files = inventory.list_files_for_article(FIGSHARE_ARTICLE)
        assert len(files) == 2
        assert files[0]["source"] == "figshare"
        assert files[1]["size_bytes"] > MAX_DOWNLOAD_BYTES

    @patch.object(AdcFileInventory, "_resolve_external_files")
    def test_external_placeholder_uses_resolver(
        self,
        mock_resolve: MagicMock,
    ) -> None:
        """Single zero-byte DOI placeholder triggers external resolution."""
        mock_resolve.return_value = [
            {"name": "a.csv", "url": "https://example/a.csv", "size_bytes": 10, "source": "dryad"},
        ]
        inventory = AdcFileInventory()
        files = inventory.list_files_for_article(DRYAD_PLACEHOLDER_ARTICLE)
        assert len(files) == 1
        mock_resolve.assert_called_once()

    def test_summarize_inventory(self) -> None:
        """Summary returns counts, formatted size, extensions, and flags."""
        inventory = AdcFileInventory()
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
        inventory = AdcFileInventory()
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

    def test_is_external_archive_for_link_only(self) -> None:
        """Link-only zero-byte files are treated as external archive."""
        inventory = AdcFileInventory()
        article = {
            "doi": "10.15482/USDA.ADC/1",
            "files": [{
                "name": "portal.html",
                "size": 0,
                "is_link_only": True,
                "download_url": "https://example.ars.usda.gov/data",
            }],
        }
        assert inventory.is_external_archive(article)
        assert inventory.list_figshare_hosted_files(article) == []

    def test_has_figshare_hosted_files(self) -> None:
        """Articles with ndownloader files are not external archive."""
        inventory = AdcFileInventory()
        assert inventory.has_figshare_hosted_files(FIGSHARE_ARTICLE) is True
        assert inventory.is_external_archive(FIGSHARE_ARTICLE) is False
        hosted = inventory.list_figshare_hosted_files(FIGSHARE_ARTICLE)
        assert len(hosted) == 2

    def test_doi_placeholder_is_external_archive(self) -> None:
        """DOI placeholders are external archive; collector must not follow the link."""
        inventory = AdcFileInventory()
        assert inventory.is_external_archive(DRYAD_PLACEHOLDER_ARTICLE) is True

    def test_list_external_reference_urls(self) -> None:
        """Link-only and DOI placeholders yield external reference URLs."""
        inventory = AdcFileInventory()
        link_only = {
            "files": [{
                "name": "portal.html",
                "size": 0,
                "is_link_only": True,
                "download_url": "https://example.ars.usda.gov/data",
            }],
        }
        assert inventory.list_external_reference_urls(link_only) == [
            "https://example.ars.usda.gov/data",
        ]
        assert inventory.external_archive_status_note(link_only) == (
            "External data URL: https://example.ars.usda.gov/data"
        )
        assert inventory.external_archive_status_note({"files": []}) is None
