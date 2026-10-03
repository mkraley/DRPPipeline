"""
Unit tests for GWDANominator.
"""

import unittest
from unittest.mock import MagicMock, patch

import requests

from utils.Logger import Logger

from publisher.GWDANominator import GWDANominator, NOMINATION_URL


class TestGWDANominator(unittest.TestCase):
    """Test cases for GWDANominator."""

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize Logger once for all tests."""
        Logger.initialize(log_level="WARNING")

    def setUp(self) -> None:
        """Start each test with an empty in-memory GWDA URL list."""
        GWDANominator._url_list_checked = True
        GWDANominator._nominated_url_keys = set()

    def test_init(self) -> None:
        """Test GWDANominator initialization."""
        mock_page = MagicMock()
        nominator = GWDANominator(mock_page, timeout=5000)
        self.assertEqual(nominator._page, mock_page)
        self.assertEqual(nominator._timeout, 5000)

    def test_nominate_empty_url_returns_false(self) -> None:
        """Test nominate returns False for empty source_url."""
        mock_page = MagicMock()
        nominator = GWDANominator(mock_page)
        success, error = nominator.nominate("")
        self.assertFalse(success)
        self.assertIn("empty", error)
        mock_page.goto.assert_not_called()

    def test_nominate_whitespace_url_returns_false(self) -> None:
        """Test nominate returns False for whitespace-only source_url."""
        mock_page = MagicMock()
        nominator = GWDANominator(mock_page)
        success, error = nominator.nominate("   ")
        self.assertFalse(success)
        mock_page.goto.assert_not_called()

    def test_nominate_missing_email_returns_false(self) -> None:
        """Test nominate returns False when email not configured."""
        mock_page = MagicMock()
        nominator = GWDANominator(mock_page)
        with patch("publisher.GWDANominator.Args", MagicMock()) as mock_args:
            mock_args.gwda_email = None
            mock_args.datalumos_username = None
            mock_args.gwda_your_name = "Test"
            mock_args.gwda_institution = "Test"
            success, error = nominator.nominate("https://example.com")
        self.assertFalse(success)
        self.assertIn("email", error.lower())

    def test_nominate_skips_url_already_on_gwda_list(self) -> None:
        """A URL already on the GWDA list is not submitted again."""
        GWDANominator._nominated_url_keys = {
            "https://irma.nps.gov/DataStore/Reference/Profile/1039540"
        }
        mock_page = MagicMock()
        nominator = GWDANominator(mock_page)
        success, error = nominator.nominate(
            "http://irma.nps.gov/DataStore/Reference/Profile/1039540/"
        )
        self.assertTrue(success)
        self.assertIsNone(error)
        mock_page.goto.assert_not_called()

    def test_url_list_failure_still_attempts_nomination(self) -> None:
        """When the GWDA list cannot be loaded, nomination continues."""
        GWDANominator._url_list_checked = False
        GWDANominator._nominated_url_keys = None
        mock_page = MagicMock()
        nominator = GWDANominator(mock_page)
        with patch(
            "publisher.GWDANominator.requests.get",
            side_effect=requests.RequestException("down"),
        ):
            with patch("publisher.GWDANominator.Args", MagicMock()) as mock_args:
                mock_args.gwda_email = None
                success, error = nominator.nominate("https://example.com/new")
        self.assertFalse(success)
        self.assertIn("email", (error or "").lower())
        mock_page.goto.assert_not_called()

    def test_nomination_url_constant(self) -> None:
        """Test NOMINATION_URL points to GWDA."""
        self.assertIn("digital2.library.unt.edu", NOMINATION_URL)
        self.assertIn("GWDA", NOMINATION_URL)
