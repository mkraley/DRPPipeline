"""Tests for ArcCandidateFetcher."""

from __future__ import annotations

from unittest.mock import MagicMock

from sourcing.ArcCandidateFetcher import AGENCY, OFFICE, ArcCandidateFetcher

SAMPLE_ARTICLE = {
    "id": 24667896,
    "title": "Example dataset",
    "url_public_html": "https://agdatacommons.nal.usda.gov/articles/dataset/Example/24667896",
    "files": [{"name": "a.csv", "size": 10, "download_url": "https://ndownloader.figshare.com/files/1"}],
}


class TestArcCandidateFetcher:
    """Tests for ARC candidate fetcher."""

    def test_build_candidate_row_basic(self) -> None:
        """ARC articles map to url/title/agency/office."""
        fetcher = ArcCandidateFetcher()
        row = fetcher.build_candidate_row(SAMPLE_ARTICLE)
        assert row is not None
        assert row["url"].endswith("/24667896")
        assert row["title"] == "Example dataset"
        assert row["agency"] == AGENCY
        assert row["office"] == OFFICE

    def test_build_candidate_row_rejects_non_arc_url(self) -> None:
        """Non-ARC Figshare URLs are filtered out."""
        fetcher = ArcCandidateFetcher()
        row = fetcher.build_candidate_row({
            **SAMPLE_ARTICLE,
            "url_public_html": "https://figshare.com/articles/dataset/X/1",
        })
        assert row is None

    def test_build_candidate_row_with_inventory(self) -> None:
        """Inventory mode populates file summary fields but not status_notes."""
        fetcher = ArcCandidateFetcher()
        row = fetcher.build_candidate_row(SAMPLE_ARTICLE, include_inventory=True)
        assert row is not None
        assert row["num_files"] == "1"
        assert row["file_size"]
        assert "status_notes" not in row

    def test_get_candidate_urls_delegates_to_api(self) -> None:
        """get_candidate_urls fetches each merged article id."""
        api = MagicMock()
        api.merge_article_ids.return_value = [24667896]
        api.fetch_article.return_value = SAMPLE_ARTICLE
        fetcher = ArcCandidateFetcher(api_client=api)
        rows, skipped = fetcher.get_candidate_urls(limit=None)
        assert skipped == 0
        assert len(rows) == 1
        assert rows[0]["url"].endswith("/24667896")
