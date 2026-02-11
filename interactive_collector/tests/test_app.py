"""
Unit tests for the Interactive Collector Flask app.
"""

import unittest
from typing import Dict
from unittest.mock import MagicMock, patch

from interactive_collector.app import (
    app,
    _base_url_for_page,
    _inject_base_into_html,
    _rewrite_links_to_app,
    _status_label,
    _unique_pdf_basename,
)


class TestBaseInjection(unittest.TestCase):
    """Tests for base URL and HTML injection."""

    def test_base_url_for_page_with_path(self) -> None:
        """Base URL ends with slash for path URLs."""
        self.assertEqual(
            _base_url_for_page("https://catalog.data.gov/dataset/accessgudid-1f586"),
            "https://catalog.data.gov/dataset/",
        )

    def test_base_url_for_page_already_trailing_slash(self) -> None:
        """URL that already ends with / is returned as-is (directory as page)."""
        self.assertEqual(
            _base_url_for_page("https://example.com/folder/"),
            "https://example.com/folder/",
        )

    def test_inject_base_into_html(self) -> None:
        """Base tag is inserted after <head>."""
        html_body = "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head><body></body></html>"
        result = _inject_base_into_html(html_body, "https://example.com/folder/page")
        self.assertIn("<base href=\"https://example.com/folder/", result)
        self.assertIn("<head>", result)
        self.assertIn("<meta charset=", result)


class TestRewriteLinks(unittest.TestCase):
    """Tests for _rewrite_links_to_app."""

    def test_rewrites_relative_link(self) -> None:
        """Relative href is resolved and rewritten with source_url, linked_url, referrer."""
        html = '<a href="/dataset/other">Link</a>'
        result = _rewrite_links_to_app(
            html,
            "https://catalog.data.gov/dataset/accessgudid-1f586",
            "http://127.0.0.1:5000",
            source_url="https://catalog.data.gov/dataset/accessgudid-1f586",
            current_page_url="https://catalog.data.gov/dataset/accessgudid-1f586",
        )
        self.assertIn("target=\"_top\"", result)
        self.assertIn("source_url=", result)
        self.assertIn("linked_url=", result)
        self.assertIn("referrer=", result)
        self.assertIn("catalog.data.gov", result)

    def test_rewrites_absolute_http_link(self) -> None:
        """Absolute http href is rewritten with pane params."""
        html = '<a href="https://catalog.data.gov/other">Link</a>'
        result = _rewrite_links_to_app(
            html,
            "https://catalog.data.gov/page",
            "http://localhost:5000",
            source_url="https://catalog.data.gov/",
            current_page_url="https://catalog.data.gov/page",
        )
        self.assertIn("http://localhost:5000/?", result)
        self.assertIn("linked_url=", result)
        self.assertIn("https%3A%2F%2Fcatalog.data.gov%2Fother", result)

    def test_leaves_anchor_unchanged(self) -> None:
        """Hash-only href is left unchanged."""
        html = '<a href="#section">Jump</a>'
        result = _rewrite_links_to_app(
            html, "https://example.com/page", "http://app",
            source_url="https://example.com/", current_page_url="https://example.com/page",
        )
        self.assertIn('href="#section"', result)
        self.assertNotIn("linked_url=", result)

    def test_leaves_mailto_unchanged(self) -> None:
        """mailto: href is left unchanged."""
        html = '<a href="mailto:foo@example.com">Email</a>'
        result = _rewrite_links_to_app(
            html, "https://example.com/page", "http://app",
            source_url="https://example.com/", current_page_url="https://example.com/page",
        )
        self.assertIn('href="mailto:foo@example.com"', result)

    def test_does_not_rewrite_link_stylesheet(self) -> None:
        """<link href="..."> for CSS is left unchanged so styles load from original server."""
        html = '<link rel="stylesheet" href="/static/style.css">'
        result = _rewrite_links_to_app(
            html, "https://catalog.data.gov/dataset/x", "http://127.0.0.1:5000",
            source_url="https://catalog.data.gov/", current_page_url="https://catalog.data.gov/dataset/x",
        )
        self.assertIn('href="/static/style.css"', result)
        self.assertNotIn("127.0.0.1:5000", result)

    def test_rewrites_catalog_link_without_pre_resolving(self) -> None:
        """Catalog.data.gov link is rewritten with the catalog URL; resolution happens on click in the route."""
        html = '<a href="https://catalog.data.gov/dataset/x/resource/abc">CSV</a>'
        result = _rewrite_links_to_app(
            html,
            "https://catalog.data.gov/dataset/x",
            "http://127.0.0.1:5000",
            source_url="https://catalog.data.gov/dataset/x",
            current_page_url="https://catalog.data.gov/dataset/x",
        )
        self.assertIn("linked_url=", result)
        self.assertIn("catalog.data.gov", result)
        self.assertIn("resource", result)
        self.assertIn("abc", result)

    def test_rewrite_includes_drpid_when_given(self) -> None:
        """When drpid is passed, rewritten links include drpid= for current project."""
        html = '<a href="https://example.com/other">Link</a>'
        result = _rewrite_links_to_app(
            html,
            "https://example.com/page",
            "http://127.0.0.1:5000",
            source_url="https://example.com/page",
            current_page_url="https://example.com/page",
            drpid="12",
        )
        self.assertIn("drpid=12", result)
        self.assertIn("linked_url=", result)


class TestUniquePdfBasename(unittest.TestCase):
    """Tests for _unique_pdf_basename."""

    def test_first_use_no_suffix(self) -> None:
        """First use of a base returns sanitized base.pdf."""
        used: Dict[str, int] = {}
        self.assertEqual(_unique_pdf_basename("My Page", used), "My_Page.pdf")

    def test_duplicate_gets_suffix(self) -> None:
        """Duplicate base names get _1, _2 suffix."""
        used: Dict[str, int] = {}
        self.assertEqual(_unique_pdf_basename("Dataset", used), "Dataset.pdf")
        self.assertEqual(_unique_pdf_basename("Dataset", used), "Dataset_1.pdf")
        self.assertEqual(_unique_pdf_basename("Dataset", used), "Dataset_2.pdf")


class TestStatusLabel(unittest.TestCase):
    """Tests for _status_label helper."""

    def test_ok(self) -> None:
        """Test 200 returns OK."""
        self.assertEqual(_status_label(200, False), "OK")

    def test_404(self) -> None:
        """Test 404 without logical returns 404."""
        self.assertEqual(_status_label(404, False), "404")

    def test_404_logical(self) -> None:
        """Test 404 with logical returns 404 (logical)."""
        self.assertEqual(_status_label(404, True), "404 (logical)")

    def test_error(self) -> None:
        """Test negative status returns Error (code)."""
        self.assertEqual(_status_label(-1, False), "Error (-1)")


class TestAppRoutes(unittest.TestCase):
    """Tests for Flask app routes."""

    def setUp(self) -> None:
        """Create test client and clear scoreboard so tests don't affect each other."""
        import interactive_collector.app as app_module
        app_module._scoreboard = []
        self.client = app.test_client()

    @patch("storage.Storage")
    def test_index_no_url_returns_form(self, mock_storage_cls: MagicMock) -> None:
        """GET / with no url param returns form and empty panes when no eligible project in Storage."""
        mock_storage_cls.list_eligible_projects.side_effect = [[], []]  # ensure_storage, get_first_eligible
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Interactive Collector", response.data)
        self.assertIn(b"name=\"url\"", response.data)
        self.assertIn(b"Go", response.data)
        self.assertIn(b"Scoreboard", response.data)
        # No current project DRPID block (avoid matching "Load DRPID:" label)
        self.assertNotIn(b'class="drpid"', response.data)

    @patch("interactive_collector.app.fetch_page_body")
    @patch("storage.Storage")
    def test_index_first_eligible_from_storage_loads_url_and_shows_drpid(
        self, mock_storage_cls: MagicMock, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """When Storage has eligible projects, GET / (no params) loads first and shows DRPID."""
        mock_fetch_page_body.return_value = (
            200,
            "<html><body>Dataset page</body></html>",
            "text/html",
            False,
        )
        project = {"DRPID": 7, "source_url": "https://catalog.data.gov/dataset/foo"}
        # First call: _ensure_storage probe (None, 0); second: _get_first_eligible ("sourcing", 1)
        mock_storage_cls.list_eligible_projects.side_effect = [[], [project]]

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"DRPID: 7", response.data)
        self.assertIn(b"https://catalog.data.gov/dataset/foo", response.data)
        self.assertIn(b"Dataset page", response.data)
        mock_fetch_page_body.assert_called_once_with("https://catalog.data.gov/dataset/foo")

    @patch("storage.Storage")
    def test_index_next_eligible_redirects_to_next_project(
        self, mock_storage_cls: MagicMock
    ) -> None:
        """GET /?next=1&current_drpid=1 redirects to URL and drpid of next eligible project."""
        next_project = {"DRPID": 5, "source_url": "https://example.com/next"}
        # First call: _ensure_storage (None, 0); second: _get_next_eligible_after ("sourcing", 200)
        mock_storage_cls.list_eligible_projects.side_effect = [
            [],
            [
                {"DRPID": 1, "source_url": "https://example.com/first"},
                next_project,
            ],
        ]

        response = self.client.get("/", query_string={"next": "1", "current_drpid": "1"})

        self.assertEqual(response.status_code, 302)
        self.assertIn("url=", response.location)
        self.assertIn("drpid=5", response.location)
        self.assertIn("example.com/next", response.location)

    @patch("storage.Storage")
    def test_index_load_drpid_redirects_to_project_url(
        self, mock_storage_cls: MagicMock
    ) -> None:
        """GET /?load_drpid=3 redirects to that project's source_url with drpid=3."""
        mock_storage_cls.get.return_value = {
            "DRPID": 3,
            "source_url": "https://catalog.data.gov/dataset/bar",
        }

        response = self.client.get("/", query_string={"load_drpid": "3"})

        self.assertEqual(response.status_code, 302)
        self.assertIn("url=", response.location)
        self.assertIn("drpid=3", response.location)
        self.assertIn("catalog.data.gov", response.location)

    def test_index_invalid_url_returns_message(self) -> None:
        """GET / with invalid url shows Invalid URL and message."""
        response = self.client.get("/", query_string={"url": "not-a-url"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid URL", response.data)
        self.assertIn(b"valid http", response.data)

    @patch("interactive_collector.app.fetch_page_body")
    def test_index_valid_url_shows_source_pane(
        self, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """GET / with valid url fetches and shows source pane with body; scoreboard has root."""
        mock_fetch_page_body.return_value = (
            200,
            "<html><body>Hello</body></html>",
            "text/html",
            False,
        )
        response = self.client.get(
            "/", query_string={"url": "https://example.com"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Scoreboard", response.data)
        self.assertIn(b"OK", response.data)
        self.assertIn(b"https://example.com", response.data)
        self.assertIn(b"<iframe", response.data)
        self.assertIn(b"srcdoc=", response.data)
        self.assertIn(b"Hello", response.data)
        self.assertIn(b"Source:", response.data)
        self.assertIn(b"Linked:", response.data)
        self.assertIn(b"example.com", response.data)
        mock_fetch_page_body.assert_called_once_with("https://example.com")

    @patch("interactive_collector.app.fetch_page_body")
    def test_index_404_shows_status(
        self, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """GET / when fetch returns 404 shows 404 status."""
        mock_fetch_page_body.return_value = (
            404,
            "Not found",
            "text/html",
            False,
        )
        response = self.client.get(
            "/", query_string={"url": "https://example.com/missing"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"404", response.data)
        self.assertNotIn(b"404 (logical)", response.data)

    @patch("interactive_collector.app.fetch_page_body")
    def test_index_logical_404_shows_label(
        self, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """GET / when fetch returns logical 404 shows 404 (logical)."""
        mock_fetch_page_body.return_value = (
            404,
            "<html>page not found</html>",
            "text/html",
            True,
        )
        response = self.client.get(
            "/", query_string={"url": "https://example.com/ghost"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"404 (logical)", response.data)

    @patch("interactive_collector.app.fetch_page_body")
    def test_index_binary_content_shows_message_not_body(
        self, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """GET / with binary Content-Type shows message in source pane, no iframe."""
        mock_fetch_page_body.return_value = (
            200,
            "",
            "application/pdf",
            False,
        )
        response = self.client.get(
            "/", query_string={"url": "https://example.com/file.pdf"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Binary content (application/pdf). Not displayed.", response.data)
        # Source pane shows message div, not srcdoc iframe
        self.assertIn(b"pane-empty", response.data)

    @patch("interactive_collector.app.fetch_page_body")
    def test_index_link_click_shows_both_panes_and_scoreboard(
        self, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """GET / with source_url, linked_url, referrer fills both panes and scoreboard."""
        def fetch_side_effect(url: str) -> tuple:
            if "source" in url or url == "https://example.com/source":
                return (200, "<html><body>Source page</body></html>", "text/html", False)
            return (200, "<html><body>Linked page</body></html>", "text/html", False)
        mock_fetch_page_body.side_effect = fetch_side_effect
        response = self.client.get(
            "/",
            query_string={
                "source_url": "https://example.com/source",
                "linked_url": "https://example.com/linked",
                "referrer": "https://example.com/source",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Source page", response.data)
        self.assertIn(b"Linked page", response.data)
        self.assertIn(b"example.com/source", response.data)
        self.assertIn(b"example.com/linked", response.data)
        self.assertEqual(mock_fetch_page_body.call_count, 2)

    @patch("interactive_collector.app._ensure_output_folder_for_drpid")
    @patch("interactive_collector.app.fetch_page_body")
    def test_index_link_click_binary_linked_shows_download_button(
        self,
        mock_fetch_page_body: unittest.mock.Mock,
        mock_ensure_output_folder: unittest.mock.Mock,
    ) -> None:
        """When linked is binary, Linked pane shows source page and auto-download runs in modal."""
        def fetch_side_effect(url: str) -> tuple:
            if "zip" in url or "linked" in url:
                return (200, b"binary", "application/zip", False)
            return (200, "<html><body>Source</body></html>", "text/html", False)
        mock_fetch_page_body.side_effect = fetch_side_effect
        mock_ensure_output_folder.return_value = "C:\\out\\DRP000001"
        response = self.client.get(
            "/",
            query_string={
                "source_url": "https://example.com/source",
                "linked_url": "https://accessgudid.nlm.nih.gov/release_files/download/gudid_daily_update_20260209.zip",
                "referrer": "https://example.com/source",
                "drpid": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Source", response.data)
        self.assertIn(b'id="auto-download-data"', response.data)
        mock_ensure_output_folder.assert_called_once()

    @patch("interactive_collector.app.fetch_page_body")
    def test_scoreboard_cleared_when_new_initial_url(
        self, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """Entering a new URL in the form (Go) clears the scoreboard and shows only that URL."""
        mock_fetch_page_body.return_value = (
            200,
            "<html><body>Page</body></html>",
            "text/html",
            False,
        )
        self.client.get("/", query_string={"url": "https://example.com/first"})
        response = self.client.get("/", query_string={"url": "https://example.com/second"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"example.com/second", response.data)
        self.assertNotIn(b"example.com/first", response.data)

    @patch("interactive_collector.app.fetch_page_body")
    def test_scoreboard_entries_are_links_when_source_set(
        self, mock_fetch_page_body: unittest.mock.Mock
    ) -> None:
        """With a source URL loaded, scoreboard entries are clickable links to the Linked pane."""
        mock_fetch_page_body.return_value = (
            200,
            "<html><body>Hi</body></html>",
            "text/html",
            False,
        )
        response = self.client.get("/", query_string={"url": "https://example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"linked_url=", response.data)
        self.assertIn(b"source_url=", response.data)
        self.assertIn(b'<a ', response.data)

    def test_save_redirects_when_no_folder_path(self) -> None:
        """POST /save with no folder_path redirects to index."""
        response = self.client.post(
            "/save",
            data={"folder_path": "", "scoreboard_urls_json": "[]", "save_url": ["0"]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/", response.location)

    def test_save_redirects_when_no_indices(self) -> None:
        """POST /save with no save_url checkboxes redirects to index."""
        response = self.client.post(
            "/save",
            data={"folder_path": "C:\\tmp\\DRP000001", "scoreboard_urls_json": "[]"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/", response.location)

    def test_scoreboard_render_with_save_form_includes_checkbox_name(self) -> None:
        """When for_save_form=True, checkboxes have name=save_url and value=index."""
        import interactive_collector.app as app_module
        app_module._scoreboard.clear()
        app_module._scoreboard.append({"url": "https://example.com", "referrer": None, "status_label": "OK", "is_dupe": False})
        from interactive_collector.app import _scoreboard_render_html
        html = _scoreboard_render_html("http://127.0.0.1:5000", "https://example.com", drpid="1", for_save_form=True)
        self.assertIn(b'name="save_url"', html.encode("utf-8"))
        self.assertIn(b'value="0"', html.encode("utf-8"))
