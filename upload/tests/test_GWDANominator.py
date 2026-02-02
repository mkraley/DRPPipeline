"""
Unit tests for GWDANominator.
"""

import unittest
from unittest.mock import MagicMock, patch

from utils.Logger import Logger

from upload.GWDANominator import GWDANominator, NOMINATION_URL


class TestGWDANominator(unittest.TestCase):
    """Test cases for GWDANominator."""

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize Logger once for all tests."""
        Logger.initialize(log_level="WARNING")

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
        with patch("upload.GWDANominator.Args") as mock_args:
            mock_args.gwda_email = None
            mock_args.datalumos_username = None
            mock_args.gwda_your_name = "Test"
            mock_args.gwda_institution = "Test"
            success, error = nominator.nominate("https://example.com")
        self.assertFalse(success)
        self.assertIn("email", error.lower())

    def test_nomination_url_constant(self) -> None:
        """Test NOMINATION_URL points to GWDA."""
        self.assertIn("digital2.library.unt.edu", NOMINATION_URL)
        self.assertIn("GWDA", NOMINATION_URL)
