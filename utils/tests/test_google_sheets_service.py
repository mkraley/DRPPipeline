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


if __name__ == "__main__":
    unittest.main()
