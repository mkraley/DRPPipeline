"""Tests for USFS catalog candidate fetcher parsing helpers."""

from sourcing.UsfsCatalogCandidateFetcher import (
    catalog_listing_url,
    extract_catalog_entries,
)

SAMPLE_LISTING_HTML = """
<div class="document">
  <h4>
    1.
    <a href="/rds/archive/catalog/RDS-2026-0018">
      30 years of litterflow biomass from the Bisley Experimental Watersheds
    </a>
  </h4>
</div>
<div class="document">
  <h4>
    2.
    <a href="/rds/archive/catalog/RDS-2026-0034">California fire severity prediction maps by region</a>
  </h4>
</div>
"""


class TestUsfsCatalogCandidateFetcher:
    def test_catalog_listing_url(self) -> None:
        assert catalog_listing_url(1) == "https://www.fs.usda.gov/rds/archive/catalog"
        assert (
            catalog_listing_url(2)
            == "https://www.fs.usda.gov/rds/archive/catalog?pageIndex=2"
        )
        assert (
            catalog_listing_url(3, page_size=50)
            == "https://www.fs.usda.gov/rds/archive/catalog?pagesize=50&pageIndex=3"
        )

    def test_extract_catalog_entries(self) -> None:
        rows = extract_catalog_entries(SAMPLE_LISTING_HTML)
        assert len(rows) == 2
        assert rows[0]["title"].startswith("30 years of litterflow biomass")
        assert rows[0]["url"] == "https://www.fs.usda.gov/rds/archive/catalog/RDS-2026-0018"
        assert rows[1]["url"].endswith("RDS-2026-0034")
