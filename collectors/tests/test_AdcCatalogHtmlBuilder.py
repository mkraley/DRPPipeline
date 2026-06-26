"""Tests for ArcCatalogHtmlBuilder."""

from __future__ import annotations

from collectors.ArcCatalogHtmlBuilder import build_catalog_html

SAMPLE_ARTICLE = {
    "title": "Example dataset",
    "description": "<p>Observational field measurements.</p>",
    "doi": "10.15482/USDA.ADC/1340592",
    "defined_type_name": "dataset",
    "published_date": "2024-02-13T15:54:24Z",
    "created_date": "2024-02-13T15:54:20Z",
    "modified_date": "2024-02-13T15:54:21Z",
    "version": 2,
    "citation": "Example, Jane (2024). Example dataset. Ag Data Commons.",
    "authors": [{"full_name": "Jane Example", "orcid_id": "0000-0001-2345-6789"}],
    "keywords": ["agriculture", "field data"],
    "tags": [{"name": "agriculture"}],
    "categories": [{"title": "Agricultural sciences"}],
    "license": {"name": "CC BY 4.0"},
    "funding": "USDA NIFA grant program",
    "funding_list": [
        {
            "grant_code": "2020-12345",
            "funder_name": "USDA NIFA",
            "title": "Example grant",
            "url": "https://example.com/grant",
        }
    ],
    "related_materials": [
        {
            "relation": "IsSupplementTo",
            "identifier_type": "DOI",
            "identifier": "10.1000/example",
            "title": "Related paper",
            "link": "https://doi.org/10.1000/example",
        }
    ],
    "references": ["https://doi.org/10.1000/example"],
    "timeline": {"posted": "2024-02-13T15:54:24", "firstOnline": "2024-02-13"},
    "files": [
        {
            "name": "data.csv",
            "size": 1024,
            "mimetype": "text/csv",
            "supplied_md5": "abc123",
            "download_url": "https://example.com/data.csv",
        }
    ],
    "custom_fields": [
        {"name": "Temporal Extent Start Date", "value": "2014-01-02"},
        {"name": "Publisher", "value": "USDA"},
    ],
}


class TestArcCatalogHtmlBuilder:
    """Tests for API-derived catalog HTML."""

    def test_build_catalog_html_includes_core_fields(self) -> None:
        """HTML contains title, DOI, files, and portal URL."""
        source_url = (
            "https://agdatacommons.nal.usda.gov/articles/dataset/Example/24667896"
        )
        html_doc = build_catalog_html(SAMPLE_ARTICLE, source_url)
        assert "Example dataset" in html_doc
        assert "10.15482/USDA.ADC/1340592" in html_doc
        assert "data.csv" in html_doc
        assert source_url in html_doc
        assert "Figshare API" in html_doc

    def test_build_catalog_html_includes_extended_sections(self) -> None:
        """HTML includes funding, related materials, history, and categories."""
        source_url = (
            "https://agdatacommons.nal.usda.gov/articles/dataset/Example/24667896"
        )
        html_doc = build_catalog_html(SAMPLE_ARTICLE, source_url)
        assert "Funding grants" in html_doc
        assert "2020-12345" in html_doc
        assert "Related materials" in html_doc
        assert "Is supplement to" in html_doc
        assert "Related paper" in html_doc
        assert "History" in html_doc
        assert "First online" in html_doc
        assert "Categories" in html_doc
        assert "Agricultural sciences" in html_doc
        assert "References" in html_doc
        assert "ORCID" in html_doc
        assert "Publisher" in html_doc

    def test_build_catalog_html_is_self_contained(self) -> None:
        """HTML uses embedded CSS only; no external JS or CSS files."""
        source_url = (
            "https://agdatacommons.nal.usda.gov/articles/dataset/Example/24667896"
        )
        html_doc = build_catalog_html(SAMPLE_ARTICLE, source_url)
        assert "<style>" in html_doc
        assert "<script" not in html_doc.lower()
        assert 'rel="stylesheet"' not in html_doc.lower()
