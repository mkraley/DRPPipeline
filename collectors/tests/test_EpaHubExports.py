"""Tests for Clip and Ship export downloads."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from collectors.EpaHubExports import EpaHubExports
from utils.Logger import Logger


def _json_response(status_code: int, payload: dict) -> MagicMock:
    """Return a mock JSON response."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"Content-Type": "application/json"}
    response.json.return_value = payload
    response.url = "https://edg-epa.hub.arcgis.com/export"
    return response


def _file_response(body: bytes) -> MagicMock:
    """Return a mock file response."""
    response = MagicMock()
    response.status_code = 200
    response.headers = {
        "Content-Type": "application/zip",
        "Content-Length": str(len(body)),
    }
    response.iter_content.return_value = [body]
    response.url = "https://files.example/layer.zip"
    return response


class TestEpaHubExports(unittest.TestCase):
    """Tests for polling Hub exports and saving files under the budget."""

    def setUp(self) -> None:
        """Initialize logging so export progress lines can be written."""
        Logger.initialize(log_level="WARNING", log_file=False)

    def test_polls_until_ready_then_saves(self) -> None:
        """A 202 generating response is followed by the download URL."""
        pending = _json_response(202, {"status": "InProgress"})
        ready = _json_response(
            200,
            {
                "status": "ready",
                "downloadUrl": "https://files.example/layer.zip",
                "contentLength": 4,
            },
        )
        body = _file_response(b"zip!")
        responses = [pending, ready, body]

        def getter(url: str, **_kwargs: object) -> MagicMock:
            del url
            return responses.pop(0)

        feature = {
            "id": "abc",
            "properties": {"type": "Feature Service", "url": ""},
        }
        service = {"layers": [{"id": 0, "name": "Sites"}], "supportedExportFormats": "csv"}
        exports = EpaHubExports(getter=getter, sleeper=lambda _sec: None, attempts=3)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            notes, planned = exports.download_all(folder, _with_service(feature, service, exports))
        self.assertEqual(notes, [])
        self.assertEqual(planned[0].relative_path, "Sites_csv.csv")
        self.assertTrue(planned[0].size_bytes)

    def test_large_export_is_deferred(self) -> None:
        """An export larger than the budget is noted and not written."""
        ready = _json_response(
            200,
            {
                "status": "ready",
                "downloadUrl": "https://files.example/big.zip",
                "contentLength": 2 * 1024**3,
            },
        )

        def getter(url: str, **_kwargs: object) -> MagicMock:
            del url
            return ready

        feature = {"id": "abc", "properties": {"type": "Service Definition", "name": "Area.sd"}}
        exports = EpaHubExports(getter=getter, sleeper=lambda _sec: None)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            notes, planned = exports.download_all(folder, feature)
        self.assertEqual(len(notes), 1)
        self.assertIn("Skipped download", notes[0])
        self.assertEqual(planned[0].relative_path, "Area.sd")
        self.assertFalse((Path(tmp) / "Area.sd").exists())

    def test_completed_result_url_is_saved(self) -> None:
        """A Completed body points at resultUrl, not downloadUrl."""
        ready = _json_response(
            200,
            {
                "status": "Completed",
                "resultUrl": "https://files.example/layer.csv",
                "contentLength": 4,
            },
        )
        body = _file_response(b"csv!")
        responses = [ready, body]

        def popping(url: str, **_kwargs: object) -> MagicMock:
            del url
            return responses.pop(0)
        feature = {
            "id": "2d718d2733a74d1689d72b922c0ac4f4_0",
            "properties": {"type": "Feature Service", "url": ""},
        }
        service = {"layers": [{"id": 0, "name": "Sites"}], "supportedExportFormats": "csv"}
        exports = EpaHubExports(getter=popping, sleeper=lambda _sec: None, attempts=3)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            notes, planned = exports.download_all(folder, _with_service(feature, service, exports))
            self.assertEqual(notes, [])
            self.assertEqual(planned[0].relative_path, "Sites_csv.csv")
            self.assertEqual((folder / "Sites_csv.csv").read_bytes(), b"csv!")

    def test_layer_suffix_is_removed_and_http_400_does_not_poll(self) -> None:
        """A feature id ending in ``_0`` uses the item id, and 400 is final."""
        seen: list[str] = []
        sleeps: list[float] = []

        def getter(url: str, **_kwargs: object) -> MagicMock:
            seen.append(url)
            return _json_response(400, {"error": "Bad Request", "statusCode": 400})

        item_id = "2d718d2733a74d1689d72b922c0ac4f4"
        feature = {
            "id": f"{item_id}_0",
            "properties": {"type": "Feature Service", "url": ""},
        }
        service = {"layers": [{"id": 0, "name": "Sites"}], "supportedExportFormats": "csv"}
        exports = EpaHubExports(
            getter=getter,
            sleeper=sleeps.append,
            attempts=5,
        )
        with tempfile.TemporaryDirectory() as tmp:
            notes, planned = exports.download_all(
                Path(tmp),
                _with_service(feature, service, exports),
            )
        self.assertEqual(notes, [])
        self.assertEqual(len(seen), 1)
        self.assertIn(f"/items/{item_id}/csv", seen[0])
        self.assertNotIn("_0", seen[0])
        self.assertEqual(sleeps, [])
        self.assertIn("HTTP 400", planned[0].access_error or "")


def _with_service(feature: dict, service: dict, exports: EpaHubExports) -> dict:
    """Make download_all see ``service`` without a live FeatureServer request."""
    exports._service_payload = lambda _folder, _feature: service  # type: ignore[method-assign]
    return feature


if __name__ == "__main__":
    unittest.main()
