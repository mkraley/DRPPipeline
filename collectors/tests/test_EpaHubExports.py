"""Tests for Clip and Ship export downloads."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from collectors.EpaHubExports import EpaHubExports


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


def _with_service(feature: dict, service: dict, exports: EpaHubExports) -> dict:
    """Make download_all see ``service`` without a live FeatureServer request."""
    exports._service_payload = lambda _folder, _feature: service  # type: ignore[method-assign]
    return feature


if __name__ == "__main__":
    unittest.main()
