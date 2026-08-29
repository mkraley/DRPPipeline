"""Tests for CollectorFactory and Collector router."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from collectors.AdcCollector import AdcCollector
from collectors.CatalogDataCollector import CatalogDataCollector
from collectors.CmsGovCollector import CmsGovCollector
from collectors.Collector import Collector
from collectors.CollectorFactory import collector_class_for_source, create_collector
from collectors.SocrataCollector import SocrataCollector
from collectors.UsfsCollector import UsfsCollector
from utils.Args import Args


class TestCollectorFactory(unittest.TestCase):
    """Tests for source-based collector resolution."""

    def setUp(self) -> None:
        """Reset Args before each test."""
        self._original_argv = sys.argv.copy()
        Args._parsed_args = {}
        Args._config = {}
        Args._initialized = False

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_adc_source_returns_adc_collector(self) -> None:
        """ADC source selects AdcCollector."""
        self.assertIs(collector_class_for_source("adc"), AdcCollector)

    def test_cdc_source_returns_socrata_collector(self) -> None:
        """CDC source selects SocrataCollector."""
        self.assertIs(collector_class_for_source("cdc"), SocrataCollector)

    def test_cms_source_returns_cms_collector(self) -> None:
        """CMS source selects CmsGovCollector."""
        self.assertIs(collector_class_for_source("cms"), CmsGovCollector)

    def test_usfs_source_returns_usfs_collector(self) -> None:
        """USFS source selects UsfsCollector."""
        self.assertIs(collector_class_for_source("usfs"), UsfsCollector)

    def test_ahrq_source_returns_catalog_collector(self) -> None:
        """AHRQ source selects CatalogDataCollector."""
        self.assertIs(collector_class_for_source("ahrq"), CatalogDataCollector)

    def test_unknown_source_raises(self) -> None:
        """Unknown source names raise ValueError."""
        with self.assertRaises(ValueError):
            collector_class_for_source("unknown")

    def test_create_collector_uses_args_source(self) -> None:
        """create_collector() reads Args.source when no override is passed."""
        sys.argv = ["test", "collector"]
        Args.initialize()
        Args._config["source"] = "adc"
        instance = create_collector()
        self.assertIsInstance(instance, AdcCollector)

    @patch("collectors.Collector.create_collector")
    def test_collector_router_delegates_run(self, mock_create: MagicMock) -> None:
        """Collector.run delegates to the resolved implementation."""
        mock_impl = MagicMock()
        mock_create.return_value = mock_impl
        Collector().run(42)
        mock_create.assert_called_once_with()
        mock_impl.run.assert_called_once_with(42)


if __name__ == "__main__":
    unittest.main()
