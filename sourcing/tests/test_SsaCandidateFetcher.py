"""Tests for SSA catalog URL helpers and candidate row building."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

from sourcing.SsaCandidateFetcher import (
    SsaCandidateFetcher,
    catalog_url_from_slug,
    has_collectible_file,
    is_file_download,
    is_html_url,
    is_public_dataset,
    slug_from_source_url,
)
from utils.Args import Args


def _result(
    *,
    slug: str = "baby-names",
    title: str = "Baby Names",
    access: str = "public",
    distributions: list[dict[str, str]] | None = None,
    identifier: str = "US-GOV-SSA-338",
) -> dict:
    """Build a minimal GSA search result."""
    return {
        "slug": slug,
        "title": title,
        "identifier": identifier,
        "dcat": {
            "accessLevel": access,
            "identifier": identifier,
            "distribution": distributions
            if distributions is not None
            else [
                {
                    "format": "ZIP",
                    "downloadURL": "https://www.ssa.gov/oact/babynames/names.zip",
                }
            ],
        },
    }


class TestSsaUrlHelpers(unittest.TestCase):
    """Tests for catalog slug helpers."""

    def test_catalog_url_from_slug(self) -> None:
        """Build canonical catalog dataset URLs."""
        self.assertEqual(
            catalog_url_from_slug("baby-names"),
            "https://catalog.data.gov/dataset/baby-names",
        )

    def test_slug_from_source_url(self) -> None:
        """Extract slugs from catalog dataset URLs."""
        self.assertEqual(
            slug_from_source_url(
                "https://catalog.data.gov/dataset/baby-names-from-social-security-card-applications-national-data"
            ),
            "baby-names-from-social-security-card-applications-national-data",
        )
        self.assertIsNone(slug_from_source_url("https://www.ssa.gov/data/"))
        self.assertIsNone(slug_from_source_url("https://catalog.data.gov/organization/ssa"))


class TestSsaCollectibleFilters(unittest.TestCase):
    """Tests for public-with-file filtering."""

    def test_is_file_download(self) -> None:
        """ZIP/PDF count; HTML landing pages do not."""
        self.assertTrue(
            is_file_download(
                {"format": "ZIP", "downloadURL": "https://www.ssa.gov/x.zip"}
            )
        )
        self.assertTrue(
            is_file_download(
                {"format": "", "downloadURL": "https://www.ssa.gov/table.xml"}
            )
        )
        self.assertFalse(
            is_file_download(
                {
                    "format": "HTML",
                    "downloadURL": "https://www.ssa.gov/policy/index.html",
                }
            )
        )
        self.assertFalse(is_file_download({"format": "CSV", "accessURL": "https://x"}))

    def test_is_html_url(self) -> None:
        """HTML format labels and .html suffixes are landing pages."""
        self.assertTrue(is_html_url("https://www.ssa.gov/x.html", "HTML"))
        self.assertTrue(is_html_url("https://www.ssa.gov/policy/index.html"))
        self.assertFalse(is_html_url("https://www.ssa.gov/names.zip", "ZIP"))

    def test_html_only_is_not_collectible(self) -> None:
        """Public HTML-only rows are skipped."""
        result = _result(
            distributions=[
                {
                    "format": "HTML",
                    "downloadURL": "https://www.ssa.gov/policy/docs/statcomps/supplement/index.html",
                }
            ]
        )
        self.assertTrue(is_public_dataset(result))
        self.assertFalse(has_collectible_file(result))

    def test_restricted_with_file_is_not_public(self) -> None:
        """Restricted-public inventory rows are skipped."""
        result = _result(access="restricted public")
        self.assertFalse(is_public_dataset(result))


class TestSsaCandidateFetcher(unittest.TestCase):
    """Tests for candidate row construction and paging."""

    def setUp(self) -> None:
        """Initialize Args defaults for fetcher construction."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "ssa_candidate_fetcher"]
        Args.initialize()

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_build_candidate_row_maps_catalog_url(self) -> None:
        """Collectible hits map to catalog.data.gov dataset URLs."""
        fetcher = SsaCandidateFetcher(client=MagicMock(), request_delay=0)
        row = fetcher.build_candidate_row(_result())
        assert row is not None
        self.assertEqual(row["url"], "https://catalog.data.gov/dataset/baby-names")
        self.assertEqual(row["title"], "Baby Names")
        self.assertEqual(row["record_id"], "baby-names")
        self.assertEqual(row["identifier"], "US-GOV-SSA-338")
        self.assertEqual(row["agency"], "Social Security Administration")

    def test_build_candidate_row_skips_html_only(self) -> None:
        """HTML-only public rows return None."""
        fetcher = SsaCandidateFetcher(client=MagicMock(), request_delay=0)
        result = _result(
            distributions=[
                {"format": "HTML", "downloadURL": "https://www.ssa.gov/x.html"}
            ]
        )
        self.assertIsNone(fetcher.build_candidate_row(result))

    def test_build_candidate_row_skips_non_public(self) -> None:
        """Non-public rows return None even when a file is listed."""
        fetcher = SsaCandidateFetcher(client=MagicMock(), request_delay=0)
        self.assertIsNone(fetcher.build_candidate_row(_result(access="non-public")))

    def test_list_dataset_rows_paginates_until_no_after(self) -> None:
        """Fetcher follows after cursors and skips non-collectible hits."""
        client = MagicMock()
        client.fetch_search_page.side_effect = [
            {
                "results": [
                    _result(slug="keep-me", title="Keep"),
                    _result(
                        slug="html-only",
                        title="Index",
                        distributions=[
                            {
                                "format": "HTML",
                                "downloadURL": "https://www.ssa.gov/index.html",
                            }
                        ],
                    ),
                ],
                "after": "cursor-2",
            },
            {
                "results": [_result(slug="year-2025", title="Year 2025")],
            },
        ]
        fetcher = SsaCandidateFetcher(client=client, request_delay=0)
        rows = fetcher.list_dataset_rows()
        self.assertEqual([row["record_id"] for row in rows], ["keep-me", "year-2025"])
        self.assertEqual(client.fetch_search_page.call_count, 2)


if __name__ == "__main__":
    unittest.main()
