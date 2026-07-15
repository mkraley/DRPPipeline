"""Unit tests for DataLumosBrowserSession auth helpers."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from upload.DataLumosBrowserSession import DataLumosBrowserSession
from utils.Args import Args
from utils.Logger import Logger


class TestDataLumosBrowserSession(unittest.TestCase):
    """Tests for session authentication helpers."""

    def setUp(self) -> None:
        """Initialize Args and logger for session methods."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "verify_upload"]
        Args.initialize()
        Logger.initialize(log_level="ERROR", log_file=False)

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_reauthenticate_clears_flag_and_logs_in(self) -> None:
        """reauthenticate forces a fresh login even when already authenticated."""
        session = DataLumosBrowserSession()
        session._authenticated = True
        session._page = MagicMock()

        def _ensure(**_kwargs: object) -> None:
            self.assertFalse(session._authenticated)
            session._authenticated = True

        with patch.object(session, "ensure_authenticated", side_effect=_ensure) as mock_ensure:
            session.reauthenticate()

        mock_ensure.assert_called_once_with(reporter=None)
        self.assertTrue(session._authenticated)

    def test_ensure_authenticated_skips_when_already_authed(self) -> None:
        """ensure_authenticated is a no-op when the session is already marked authenticated."""
        session = DataLumosBrowserSession()
        session._authenticated = True

        with patch(
            "upload.DataLumosAuthenticator.DataLumosAuthenticator"
        ) as mock_auth_cls:
            session.ensure_authenticated()

        mock_auth_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
