"""Tests for utils.google_sheets_service."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestBuildSheetsV4Service(unittest.TestCase):
    """build_sheets_v4_service delegates to discovery build with correct wiring."""

    def test_without_ca_bundle_uses_credentials_only(self) -> None:
        from utils.google_sheets_service import build_sheets_v4_service

        creds = MagicMock()
        mock_service = MagicMock()
        with patch("utils.google_sheets_service._resolve_ssl_ca_bundle_path", return_value=None), patch(
            "utils.google_sheets_service._ensure_system_trust_store"
        ) as mock_trust, patch("googleapiclient.discovery.build", return_value=mock_service) as mock_build:
            out = build_sheets_v4_service(creds, cache_discovery=False, ssl_ca_bundle=None)
        self.assertIs(out, mock_service)
        mock_trust.assert_called_once()
        mock_build.assert_called_once_with(
            "sheets",
            "v4",
            credentials=creds,
            cache_discovery=False,
        )

    def test_with_resolved_bundle_uses_authorized_http(self) -> None:
        from utils.google_sheets_service import build_sheets_v4_service

        creds = MagicMock()
        mock_service = MagicMock()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write("# dummy\n")
            pem_path = Path(f.name)
        try:
            with patch(
                "utils.google_sheets_service._resolve_ssl_ca_bundle_path",
                return_value=pem_path.resolve(),
            ), patch("googleapiclient.discovery.build", return_value=mock_service) as mock_build, patch(
                "httplib2.Http"
            ) as mock_http_cls, patch(
                "google_auth_httplib2.AuthorizedHttp"
            ) as mock_auth_cls:
                mock_auth_inst = MagicMock()
                mock_auth_cls.return_value = mock_auth_inst
                out = build_sheets_v4_service(creds, cache_discovery=False, ssl_ca_bundle=None)
            self.assertIs(out, mock_service)
            mock_http_cls.assert_called_once_with(ca_certs=str(pem_path.resolve()))
            mock_build.assert_called_once_with(
                "sheets",
                "v4",
                http=mock_auth_inst,
                cache_discovery=False,
            )
        finally:
            pem_path.unlink(missing_ok=True)

    def test_with_ca_bundle_uses_authorized_http(self) -> None:
        from utils.google_sheets_service import build_sheets_v4_service

        creds = MagicMock()
        mock_service = MagicMock()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write("# dummy\n")
            pem_path = Path(f.name)
        try:
            with patch("googleapiclient.discovery.build", return_value=mock_service) as mock_build, patch(
                "httplib2.Http"
            ) as mock_http_cls, patch(
                "google_auth_httplib2.AuthorizedHttp"
            ) as mock_auth_cls:
                mock_auth_inst = MagicMock()
                mock_auth_cls.return_value = mock_auth_inst
                out = build_sheets_v4_service(
                    creds,
                    cache_discovery=True,
                    ssl_ca_bundle=pem_path,
                )
            self.assertIs(out, mock_service)
            mock_http_cls.assert_called_once_with(ca_certs=str(pem_path.resolve()))
            mock_auth_cls.assert_called_once()
            mock_build.assert_called_once_with(
                "sheets",
                "v4",
                http=mock_auth_inst,
                cache_discovery=True,
            )
        finally:
            pem_path.unlink(missing_ok=True)


class TestExecuteSheetsRequest(unittest.TestCase):
    """execute_sheets_request retries HTTP 429 with backoff."""

    def test_sheets_retry_after_uses_header(self) -> None:
        from utils.google_sheets_service import sheets_retry_after_seconds

        exc = MagicMock()
        exc.resp = {"retry-after": "12"}
        self.assertEqual(sheets_retry_after_seconds(exc, 5.0), 12.0)

    def test_sheets_retry_after_floors_fallback_at_sixty(self) -> None:
        from utils.google_sheets_service import sheets_retry_after_seconds

        exc = MagicMock()
        exc.resp = {}
        self.assertEqual(sheets_retry_after_seconds(exc, 15.0), 60.0)

    def test_execute_retries_429_then_succeeds(self) -> None:
        from googleapiclient.errors import HttpError
        from utils.Logger import Logger
        from utils.google_sheets_service import execute_sheets_request

        Logger.initialize(log_level="WARNING")

        resp_429 = MagicMock()
        resp_429.status = 429
        resp_429.reason = "RATE_LIMIT_EXCEEDED"
        resp_429.get = MagicMock(return_value=None)
        err = HttpError(resp=resp_429, content=b"quota")

        request = MagicMock()
        request.execute.side_effect = [err, {"ok": True}]

        with patch("utils.google_sheets_service.time.sleep") as mock_sleep:
            result = execute_sheets_request(
                request,
                max_retries=2,
                initial_backoff_seconds=60.0,
                operation_label="test sheets",
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(request.execute.call_count, 2)
        mock_sleep.assert_called_once()
        self.assertGreaterEqual(mock_sleep.call_args[0][0], 60.0)

    def test_execute_reraises_non_429(self) -> None:
        from googleapiclient.errors import HttpError
        from utils.google_sheets_service import execute_sheets_request

        resp = MagicMock()
        resp.status = 403
        err = HttpError(resp=resp, content=b"forbidden")
        request = MagicMock()
        request.execute.side_effect = err

        with self.assertRaises(HttpError):
            execute_sheets_request(request, max_retries=2)


if __name__ == "__main__":
    unittest.main()
