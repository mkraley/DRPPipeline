"""Tests for Globus refresh-token helper script."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from debug.globus_auth_refresh_token import extract_transfer_refresh_token


class TestExtractTransferRefreshToken(unittest.TestCase):
    """Tests for extract_transfer_refresh_token."""

    def test_prefers_transfer_resource_server(self) -> None:
        """Transfer server refresh token is returned when present."""
        tokens = SimpleNamespace(
            by_resource_server={
                "auth.globus.org": {"refresh_token": "auth-refresh"},
                "transfer.api.globus.org": {"refresh_token": "transfer-refresh"},
            }
        )
        self.assertEqual(extract_transfer_refresh_token(tokens), "transfer-refresh")

    def test_falls_back_to_any_refresh_token(self) -> None:
        """Any refresh token is used when transfer server entry is missing."""
        tokens = SimpleNamespace(
            by_resource_server={
                "auth.globus.org": {"refresh_token": "auth-refresh"},
            }
        )
        self.assertEqual(extract_transfer_refresh_token(tokens), "auth-refresh")


if __name__ == "__main__":
    unittest.main()
