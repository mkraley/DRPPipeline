"""Tests for AdcApiClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sourcing.AdcApiClient import AdcApiClient, article_id_from_source_url

SAMPLE_SEARCH_RESPONSE = [
    {
        "id": 24667896,
        "url_public_html": (
            "https://agdatacommons.nal.usda.gov/articles/dataset/Example/24667896"
        ),
    },
    {
        "id": 999,
        "url_public_html": "https://figshare.com/articles/dataset/Other/999",
    },
]


class TestAdcApiClient:
    """Tests for Figshare ADC API helpers."""

    def test_article_id_from_source_url(self) -> None:
        """Numeric article ID is parsed from the portal URL tail."""
        url = "https://agdatacommons.nal.usda.gov/articles/dataset/Example/24667896"
        assert article_id_from_source_url(url) == 24667896
        assert article_id_from_source_url("https://example.com/no-id") is None

    def test_adc_article_id_from_summary_filters_non_adc_urls(self) -> None:
        """Only Ag Data Commons portal URLs are kept."""
        client = AdcApiClient(request_delay=0)
        adc_id = client._adc_article_id_from_summary(SAMPLE_SEARCH_RESPONSE[0])
        other = client._adc_article_id_from_summary(SAMPLE_SEARCH_RESPONSE[1])
        assert adc_id == 24667896
        assert other is None

    @patch("sourcing.AdcApiClient.requests.post")
    def test_list_adc_article_ids_paginates(self, mock_post: MagicMock) -> None:
        """Search pagination stops on a short final page."""
        full_page = [
            {
                "id": 24667896,
                "url_public_html": (
                    "https://agdatacommons.nal.usda.gov/articles/dataset/Example/24667896"
                ),
            },
        ] * 100
        first = MagicMock()
        first.json.return_value = full_page
        first.raise_for_status.return_value = None
        second = MagicMock()
        second.json.return_value = []
        second.raise_for_status.return_value = None
        mock_post.side_effect = [first, second]

        client = AdcApiClient(request_delay=0)
        ids = client.list_adc_article_ids(max_pages=5)
        assert ids == [24667896]
        assert mock_post.call_count == 2

    @patch("sourcing.AdcApiClient.requests.post")
    def test_list_adc_article_ids_respects_limit(self, mock_post: MagicMock) -> None:
        """Limit stops search after enough ADC hits without scanning the full catalog."""
        batch = [
            {
                "id": index,
                "url_public_html": (
                    f"https://agdatacommons.nal.usda.gov/articles/dataset/X/{index}"
                ),
            }
            for index in range(1, 51)
        ]
        response = MagicMock()
        response.json.return_value = batch
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        client = AdcApiClient(request_delay=0)
        ids = client.list_adc_article_ids(limit=25)
        assert ids == list(range(1, 26))
        mock_post.assert_called_once()

    @patch("sourcing.AdcApiClient.requests.get")
    def test_fetch_article(self, mock_get: MagicMock) -> None:
        """fetch_article returns the Figshare JSON body."""
        response = MagicMock()
        response.json.return_value = {"id": 1, "title": "Example"}
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        article = AdcApiClient(request_delay=0).fetch_article(1)
        assert article["title"] == "Example"

    @patch.object(AdcApiClient, "list_adc_article_ids", return_value=[1, 2, 3])
    @patch.object(AdcApiClient, "harvest_portal_article_ids")
    def test_merge_article_ids_search_only_by_default(
        self,
        mock_oai: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """Full enumeration uses USDA.ADC search only unless include_oai is set."""
        client = AdcApiClient(request_delay=0)
        assert client.merge_article_ids() == [1, 2, 3]
        mock_search.assert_called_once_with(max_pages=None)
        mock_oai.assert_not_called()

    @patch.object(AdcApiClient, "list_adc_article_ids", return_value=[1, 2])
    @patch.object(AdcApiClient, "harvest_portal_article_ids", return_value=[2, 3])
    def test_merge_article_ids_unions_oai_when_requested(
        self,
        mock_oai: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """include_oai merges search hits with OAI portal_1059 identifiers."""
        client = AdcApiClient(request_delay=0)
        assert client.merge_article_ids(include_oai=True) == [1, 2, 3]
        mock_search.assert_called_once_with(max_pages=None)
        mock_oai.assert_called_once()

    @patch.object(AdcApiClient, "list_adc_article_ids", return_value=[10, 20])
    @patch.object(AdcApiClient, "harvest_portal_article_ids")
    def test_merge_article_ids_limit_uses_search_only(
        self,
        mock_oai: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """--num-rows sampling stops after the search limit without OAI."""
        client = AdcApiClient(request_delay=0)
        assert client.merge_article_ids(limit=2) == [10, 20]
        mock_search.assert_called_once_with(max_pages=None, limit=2)
        mock_oai.assert_not_called()
