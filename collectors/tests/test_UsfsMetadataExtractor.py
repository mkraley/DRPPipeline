"""Tests for UsfsMetadataExtractor parsing helpers."""

from collectors.UsfsMetadataExtractor import (
    DATA_TYPE_AGGREGATE,
    DATA_TYPE_EXPERIMENTAL,
    DATA_TYPE_GIS,
    DATA_TYPE_OBSERVATIONAL,
    DATA_TYPE_PROGRAM_SOURCE,
    DATA_TYPE_SURVEY,
    infer_data_types,
    merge_usfs_metadata,
    normalize_keywords,
    normalize_temporal_date,
    parse_data_access_links,
    parse_data_type_signals,
    parse_detail_page,
    parse_download_count,
    parse_human_size,
    parse_metadata_page,
    rds_id_from_source_url,
)

DATA_ACCESS_BOX_ZIPS_HTML = """
<dl>
<dt>Data Access:</dt>
<dd class="product">
<ul>
<li>View <a href="/rds/archive/products/RDS-2026-0016/_metadata_RDS-2026-0016.html">metadata</a> (HTML)</li>
<li>View <a href="/rds/archive/products/RDS-2026-0016/_fileindex_RDS-2026-0016.html">file index</a> (HTML)</li>
<li>Download all files below for the complete publication:
<ul>
<li><a href="/rds/archive/products/RDS-2026-0016/RDS-2026-0016_Metadata_Fileindex.zip">RDS-2026-0016_Metadata_Fileindex.zip</a><em>(26.25 KB;</em></li>
<li><a href="https://usfs-public.box.com/shared/static/abc.zip">RDS-2026-0016_Data_FuelMap2020.zip</a><em>(30.8 GB;</em></li>
<li><a href="https://usfs-public.box.com/shared/static/def.zip">RDS-2026-0016_Data_FuelMap2022.zip</a><em>(30.9 GB;</em></li>
</ul>
</li>
</ul>
</dd>
</dl>
"""

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
<li><a href="/rds/archive/products/RDS-2026-0018/RDS-2026-0018.zip">RDS-2026-0018.zip</a><em>(264.95 MB;</em></li>
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

METADATA_HTML_YMD = """
<dt>Geospatial_Data_Presentation_Form:tabular digital data</dt>
<dt>Beginning_Date:201606</dt>
<dt>Ending_Date:201707</dt>
<dt>Beginning_Date:19990803</dt>
<dt>Ending_Date:20010915</dt>
"""

METADATA_HTML_GEO = """
<dt>Description_of_Geographic_Extent:</dt>
<dd>Study area near Fraser, Colorado.</dd>
<dt><i>West_Bounding_Coordinate: </i>-105.5</dt>
<dt><i>East_Bounding_Coordinate: </i>-105.0</dt>
<dt><i>North_Bounding_Coordinate: </i>39.9</dt>
<dt><i>South_Bounding_Coordinate: </i>39.5</dt>
<dt><i>Place_Keyword: </i>Puerto Rico</dt>
<dt><i>Place_Keyword: </i>Luquillo Experimental Forest</dt>
"""


class TestUsfsMetadataExtractor:
    def test_rds_id_from_source_url(self) -> None:
        assert (
            rds_id_from_source_url("https://www.fs.usda.gov/rds/archive/catalog/RDS-2026-0018")
            == "RDS-2026-0018"
        )
        assert (
            rds_id_from_source_url("https://www.fs.usda.gov/rds/archive/catalog/EFR-2026-001")
            == "EFR-2026-001"
        )

    def test_normalize_keywords_splits_and_strips_ampersands(self) -> None:
        raw = (
            "inlandWaters; Ecology, Ecosystems, & Environment; "
            "Hydrology, watersheds, sedimentation; organic matter"
        )
        assert normalize_keywords(raw) == (
            "inlandWaters, Ecology, Ecosystems, Environment, "
            "Hydrology, watersheds, sedimentation, organic matter"
        )
        assert normalize_keywords("environment; Fire; Ecology") == "environment, Fire, Ecology"

    def test_parse_human_size(self) -> None:
        assert parse_human_size("26.25 KB") == int(26.25 * 1024)
        assert parse_human_size("30.8 GB") == int(30.8 * 1024**3)

    def test_normalize_temporal_date(self) -> None:
        assert normalize_temporal_date("1987") == "1987"
        assert normalize_temporal_date("201606") == "2016-06-01"
        assert normalize_temporal_date("19990803") == "1999-08-03"
        assert normalize_temporal_date("  2025  ") == "2025"

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
        name, url, size_bytes = links["publication_files"][0]
        assert name == "RDS-2026-0018.zip"
        assert url.endswith("/RDS-2026-0018.zip")
        assert size_bytes == parse_human_size("264.95 MB")

    def test_parse_data_access_links_includes_box_com_zips(self) -> None:
        links = parse_data_access_links(
            DATA_ACCESS_BOX_ZIPS_HTML,
            "https://www.fs.usda.gov/rds/archive/catalog/RDS-2026-0016",
        )
        names = [name for name, _url, _size in links["publication_files"]]
        assert names == [
            "RDS-2026-0016_Metadata_Fileindex.zip",
            "RDS-2026-0016_Data_FuelMap2020.zip",
            "RDS-2026-0016_Data_FuelMap2022.zip",
        ]
        assert links["publication_files"][1][1].startswith("https://usfs-public.box.com/")
        assert links["publication_files"][1][2] == parse_human_size("30.8 GB")

    def test_parse_metadata_page(self) -> None:
        result = parse_metadata_page(METADATA_HTML)
        assert "office" not in result  # FGDC page does not set office
        assert result["time_start"] == "1987"
        assert result["time_end"] == "2018"
        assert "data_types" not in result

    def test_parse_metadata_page_normalizes_ymd(self) -> None:
        result = parse_metadata_page(METADATA_HTML_YMD)
        assert result["time_start"] == "2016-06-01"
        assert result["time_end"] == "2017-07-01"

    def test_parse_metadata_page_geographic_fields(self) -> None:
        result = parse_metadata_page(METADATA_HTML_GEO)
        assert result["geographic_extent_description"] == "Study area near Fraser, Colorado."
        assert result["place_keywords"] == ["Puerto Rico", "Luquillo Experimental Forest"]
        assert result["bounding_box"] == {
            "west": -105.5,
            "east": -105.0,
            "north": 39.9,
            "south": 39.5,
        }

    def test_merge_usfs_metadata_prefers_metadata_dates(self) -> None:
        detail = {"title": "T", "time_end": "2026", "summary": "S"}
        metadata = {"time_start": "1987", "time_end": "2018", "data_types": "tabular"}
        merged = merge_usfs_metadata(detail, metadata)
        assert merged["time_start"] == "1987"
        assert merged["time_end"] == "2018"
        assert "data_types" not in merged
        assert merged["summary"] == "S"

    def test_infer_data_types_litterflow_observational(self) -> None:
        title = (
            "30 years of litterflow biomass from the Bisley Experimental Watersheds "
            "in the Luquillo Experimental Forest"
        )
        summary = (
            "Leaf litter was collected every 2 weeks for over 30 years and weighed. "
            "The data file includes the biweekly weights of each compartment."
        )
        assert infer_data_types(title, summary) == DATA_TYPE_OBSERVATIONAL

    def test_infer_data_types_fire_severity_gis_and_code(self) -> None:
        title = "California fire severity prediction maps by region"
        summary = (
            "This data publication contains a spatial database of potential fire severity "
            "raster datasets for California. The package includes R scripts and Google Earth "
            "Engine scripts used to produce the fire severity rasters."
        )
        metadata_html = """
        <dt>Direct_Spatial_Reference_Method:Raster</dt>
        <dt>Format_Name:GDB</dt>
        <dt>Format_Name:R</dt>
        """
        result = infer_data_types(title, summary, metadata_html)
        assert result == f"{DATA_TYPE_PROGRAM_SOURCE}; {DATA_TYPE_GIS}"

    def test_infer_data_types_ghg_aggregate(self) -> None:
        summary = (
            "Included in this data publication are 33 tables of estimates and 4 tables of "
            "quantitative uncertainties."
        )
        assert infer_data_types("GHG emissions and removals", summary) == DATA_TYPE_AGGREGATE

    def test_infer_data_types_visitor_survey(self) -> None:
        title = "Stephen Mather Wilderness: Visitor survey data collected in 2024"
        summary = (
            "These data (n = 766) include both overnight and day users, with insights into "
            "visitor characteristics including demographics and use patterns."
        )
        assert infer_data_types(title, summary) == DATA_TYPE_SURVEY

    def test_infer_data_types_historical_documents_blank(self) -> None:
        summary = (
            "This package includes historical documents such as letters, reports, notes, "
            "memorandums of understanding, and research plans."
        )
        assert infer_data_types("Historical background information", summary) == ""

    def test_infer_data_types_suppression_spending_code_and_admin(self) -> None:
        summary = (
            "This data publication contains the Stata code as well as the historical data "
            "input and multiple modeling output files. Historical suppression spending data "
            "span 2005-2020 for the Forest Service."
        )
        metadata_html = "<dt>Format_Name:DO</dt>"
        result = infer_data_types("Wildfire suppression spending projections", summary, metadata_html)
        assert DATA_TYPE_PROGRAM_SOURCE in result.split("; ")
        assert "Administrative records data" in result.split("; ")

    def test_infer_data_types_ponderosa_observational_and_experimental(self) -> None:
        title = (
            "Ponderosa pine growth and yield measurements on Black Hills Experimental Forest "
            "growing stock level plots"
        )
        summary = (
            "Plots were measured approximately every five years and field measurements included "
            "tree diameter, height, and crown length."
        )
        result = infer_data_types(title, summary)
        assert DATA_TYPE_OBSERVATIONAL in result.split("; ")
        assert DATA_TYPE_EXPERIMENTAL in result.split("; ")

    def test_parse_data_type_signals(self) -> None:
        metadata_html = """
        <dt>Direct_Spatial_Reference_Method:Raster</dt>
        <dt>Geospatial_Data_Presentation_Form:raster digital data</dt>
        <dt>Format_Name:TIFF</dt>
        <dt>Entity_and_Attribute_Overview:</dt>
        <dd>GeoTIFF raster layers for each region.</dd>
        """
        signals = parse_data_type_signals(metadata_html)
        assert signals["direct_spatial_raster"] is True
        assert "raster digital data" in signals["presentation_forms"]
        assert "TIFF" in signals["format_names"]
        assert "geotiff" in signals["entity_overview"]
