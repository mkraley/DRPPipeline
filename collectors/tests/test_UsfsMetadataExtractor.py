"""Tests for UsfsMetadataExtractor parsing helpers."""

from collectors.UsfsMetadataExtractor import (
    merge_usfs_metadata,
    parse_data_access_links,
    parse_detail_page,
    parse_download_count,
    parse_metadata_page,
    rds_id_from_source_url,
)

DETAIL_HTML = """
<html><head>
<meta name="citation_doi" content="https://doi.org/10.2737/RDS-2026-0018">
</head><body>
<dl>
<dt>Title:</dt><dd>Sample dataset title</dd>
<dt>Author(s):</dt><dd>Author One; Author Two</dd>
<dt>Publication Year:</dt><dd>2026</dd>
<dt>Abstract:</dt><dd>Sample abstract text.</dd>
<dt>Keywords:</dt><dd>environment; Fire; Ecology</dd>
<dt>Metrics:</dt><dd>Visit count : 140 Download count: 7 More details</dd>
<dt>Data Access:</dt>
<dd class="product">
<ul>
<li>View <a href="/rds/archive/products/RDS-2026-0018/_metadata_RDS-2026-0018.html">metadata</a> (HTML)</li>
<li>View <a href="/rds/archive/products/RDS-2026-0018/_fileindex_RDS-2026-0018.html">file index</a> (HTML)</li>
<li>Download all files below for the complete publication:
<ul>
<li><a href="/rds/archive/products/RDS-2026-0018/RDS-2026-0018.zip">RDS-2026-0018.zip</a></li>
</ul>
</li>
</ul>
</dd>
</dl>
</body></html>
"""

METADATA_HTML = """
<dt>Geospatial_Data_Presentation_Form:tabular digital data</dt>
<dt>Beginning_Date:1987</dt>
<dt>Ending_Date:2018</dt>
<dt>Beginning_Date:1999</dt>
<dt>Ending_Date:2020</dt>
"""


class TestUsfsMetadataExtractor:
    def test_rds_id_from_source_url(self) -> None:
        assert (
            rds_id_from_source_url("https://www.fs.usda.gov/rds/archive/catalog/RDS-2026-0018")
            == "RDS-2026-0018"
        )

    def test_parse_download_count(self) -> None:
        assert parse_download_count("Visit count : 14 0 Download count: 1 More details") == 1
        assert parse_download_count("Download count: 13") == 13
        assert parse_download_count("no metrics") is None

    def test_parse_detail_page(self) -> None:
        result = parse_detail_page(
            DETAIL_HTML,
            "https://www.fs.usda.gov/rds/archive/catalog/RDS-2026-0018",
        )
        assert result["title"] == "Sample dataset title"
        assert result["summary"] == "Sample abstract text."
        assert result["keywords"] == "environment, Fire, Ecology"
        assert result["agency"] == "US Department of Agriculture"
        assert result["office"] == "US Forest Service"
        assert result["downloads"] == 7
        assert "DOI:" in result["collection_notes"]
        assert "Authors:" in result["collection_notes"]
        assert result["time_end"] == "2026"

    def test_parse_data_access_links(self) -> None:
        links = parse_data_access_links(
            DETAIL_HTML,
            "https://www.fs.usda.gov/rds/archive/catalog/RDS-2026-0018",
        )
        assert links["metadata_url"].endswith("_metadata_RDS-2026-0018.html")
        assert links["fileindex_url"].endswith("_fileindex_RDS-2026-0018.html")
        assert links["publication_files"] == [
            (
                "RDS-2026-0018.zip",
                "https://www.fs.usda.gov/rds/archive/products/RDS-2026-0018/RDS-2026-0018.zip",
            )
        ]

    def test_parse_metadata_page(self) -> None:
        result = parse_metadata_page(METADATA_HTML)
        assert "office" not in result  # FGDC page does not set office
        assert result["time_start"] == "1987"
        assert result["time_end"] == "2018"
        assert result["data_types"] == "tabular"

    def test_merge_usfs_metadata_prefers_metadata_dates(self) -> None:
        detail = {"title": "T", "time_end": "2026", "summary": "S"}
        metadata = {"time_start": "1987", "time_end": "2018", "data_types": "tabular"}
        merged = merge_usfs_metadata(detail, metadata)
        assert merged["time_start"] == "1987"
        assert merged["time_end"] == "2018"
        assert merged["data_types"] == "tabular"
        assert merged["summary"] == "S"
