"""Tests for AdcMetadataExtractor."""

from __future__ import annotations

from collectors.AdcMetadataExtractor import (
    bounding_box_from_geojson,
    custom_field_value,
    extract_collection_notes,
    extract_metadata,
    extract_temporal_fields,
    infer_adc_data_types,
    normalize_geographic_coverage,
)

SAMPLE_GEOJSON = (
    '{"type":"FeatureCollection","features":[{"geometry":{"type":"Point",'
    '"coordinates":[-77.87,39.35]},"type":"Feature","properties":{}}]}'
)

SAMPLE_ARTICLE = {
    "id": 24667896,
    "title": "Example dataset",
    "description": "Observational field measurements from plot-level sampling.",
    "defined_type_name": "dataset",
    "doi": "10.15482/USDA.ADC/1340592",
    "tags": [{"name": "agriculture"}, {"name": "soil"}],
    "files": [{"name": "data.csv", "size": 100, "download_url": "https://example/file"}],
    "custom_fields": [
        {"name": "Temporal Extent Start Date", "value": "2014-01-02"},
        {"name": "Temporal Extent End Date", "value": "2015-11-30"},
        {"name": "Geographic Coverage", "value": SAMPLE_GEOJSON},
        {
            "name": "Preferred dataset citation",
            "value": "Example (2022). Ag Data Commons. https://doi.org/10.15482/USDA.ADC/1340592",
        },
        {"name": "ISO Topic Category", "value": ["farming"]},
    ],
}


class TestAdcMetadataExtractor:
    """Tests for Figshare metadata mapping."""

    def test_custom_field_value(self) -> None:
        """Custom fields are read by label."""
        assert custom_field_value(SAMPLE_ARTICLE, "Temporal Extent Start Date") == "2014-01-02"
        assert custom_field_value(SAMPLE_ARTICLE, "Missing") == ""

    def test_extract_collection_notes_includes_doi(self) -> None:
        """DOI is recorded in collection_notes."""
        notes = extract_collection_notes(SAMPLE_ARTICLE)
        assert "DOI: 10.15482/USDA.ADC/1340592" in notes
        assert "Citation:" in notes

    def test_extract_temporal_fields(self) -> None:
        """Explicit start and end dates are preserved."""
        temporal = extract_temporal_fields(SAMPLE_ARTICLE)
        assert temporal == {"time_start": "2014-01-02", "time_end": "2015-11-30"}

    def test_extract_temporal_fields_infers_end_from_filenames(self) -> None:
        """Missing end date is inferred from embedded dates in file names."""
        article = {
            **SAMPLE_ARTICLE,
            "files": [
                {"name": "2019_15-min_weather_SWMRU_CPRL.xlsx", "size": 100},
                {"name": "2023_15-min_weather_SWMRU_CPRL.xlsx", "size": 100},
            ],
            "custom_fields": [
                {"name": "Temporal Extent Start Date", "value": "1987-01-01"},
            ],
        }
        temporal = extract_temporal_fields(article)
        assert temporal["time_start"] == "1987-01-01"
        assert temporal["time_end"] == "2023"

    def test_extract_temporal_fields_pairs_when_no_filename_dates(self) -> None:
        """Start-only metadata copies start to end when filenames lack dates."""
        article = {
            **SAMPLE_ARTICLE,
            "files": [{"name": "data.csv", "size": 100}],
            "custom_fields": [
                {"name": "Temporal Extent Start Date", "value": "2014-01-02"},
            ],
        }
        temporal = extract_temporal_fields(article)
        assert temporal == {"time_start": "2014-01-02", "time_end": "2014-01-02"}

    def test_bounding_box_from_geojson(self) -> None:
        """GeoJSON point coverage yields a bounding box."""
        bbox = bounding_box_from_geojson(SAMPLE_GEOJSON)
        assert bbox is not None
        assert bbox["west"] == -77.87
        assert bbox["north"] == 39.35

    def test_normalize_geographic_coverage(self) -> None:
        """GeoJSON coverage normalizes to ICPSR terms."""
        geo = normalize_geographic_coverage(SAMPLE_ARTICLE)
        assert geo.geographic_coverage

    def test_infer_adc_data_types_from_description(self) -> None:
        """Observational language in the description yields a data type."""
        data_types = infer_adc_data_types(SAMPLE_ARTICLE)
        assert data_types

    def test_extract_metadata(self) -> None:
        """Full metadata extraction populates Storage fields."""
        metadata = extract_metadata(SAMPLE_ARTICLE)
        assert metadata["title"] == "Example dataset"
        assert metadata["summary"] == (
            "<p>Observational field measurements from plot-level sampling.</p>"
        )
        assert "agriculture" in metadata["keywords"]
        assert metadata["collection_notes"]
        assert metadata["time_start"] == "2014-01-02"
        assert metadata.get("geographic_coverage")
        assert metadata.get("data_types")
