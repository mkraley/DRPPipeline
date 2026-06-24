"""Tests for ArcMetadataExtractor."""

from __future__ import annotations

from collectors.ArcMetadataExtractor import extract_metadata


class TestArcMetadataExtractor:
    """Tests for Figshare metadata mapping."""

    def test_extract_metadata(self) -> None:
        """Title, summary, and tag keywords are mapped to Storage fields."""
        article = {
            "title": "Example dataset",
            "description": "A short summary.",
            "tags": [{"name": "agriculture"}, {"name": "soil"}],
        }
        metadata = extract_metadata(article)
        assert metadata["title"] == "Example dataset"
        assert metadata["summary"] == "A short summary."
        assert "agriculture" in metadata["keywords"]
        assert "soil" in metadata["keywords"]
