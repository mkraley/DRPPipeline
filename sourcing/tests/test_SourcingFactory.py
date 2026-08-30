"""
Unit tests for SourcingFactory and Sourcing router.
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from sourcing.AdcSourcing import AdcSourcing
from sourcing.BtsSourcing import BtsSourcing
from sourcing.Sourcing import Sourcing
from sourcing.SourcingFactory import create_sourcing, sourcing_class_for_source
from sourcing.SpreadsheetSourcing import SpreadsheetSourcing
from utils.Args import Args


class TestSourcingFactory(unittest.TestCase):
    """Tests for source-based sourcing resolution."""

    def setUp(self) -> None:
        """Reset Args before each test."""
        self._original_argv = sys.argv.copy()
        Args._parsed_args = {}
        Args._config = {}
        Args._initialized = False

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_adc_source_returns_adc_sourcing(self) -> None:
        """ADC source selects AdcSourcing."""
        self.assertIs(sourcing_class_for_source("adc"), AdcSourcing)

    def test_bts_source_returns_bts_sourcing(self) -> None:
        """BTS source selects BtsSourcing."""
        self.assertIs(sourcing_class_for_source("bts"), BtsSourcing)

    def test_spreadsheet_sources_return_spreadsheet_sourcing(self) -> None:
        """Sheet-based sources select SpreadsheetSourcing."""
        for source in ("ahrq", "cdc", "cms", "dol", "usfs"):
            with self.subTest(source=source):
                self.assertIs(
                    sourcing_class_for_source(source),
                    SpreadsheetSourcing,
                )

    def test_unknown_source_raises(self) -> None:
        """Unknown source names raise ValueError."""
        with self.assertRaises(ValueError):
            sourcing_class_for_source("unknown")

    def test_create_sourcing_uses_args_source(self) -> None:
        """create_sourcing() reads Args.source when no override is passed."""
        sys.argv = ["test", "sourcing"]
        Args.initialize()
        Args._config["source"] = "adc"
        instance = create_sourcing()
        self.assertIsInstance(instance, AdcSourcing)

    @patch("sourcing.Sourcing.create_sourcing")
    def test_sourcing_router_delegates_run(self, mock_create: MagicMock) -> None:
        """Sourcing.run delegates to the resolved implementation."""
        mock_impl = MagicMock()
        mock_create.return_value = mock_impl
        Sourcing().run(-1)
        mock_create.assert_called_once_with()
        mock_impl.run.assert_called_once_with(-1)


if __name__ == "__main__":
    unittest.main()
