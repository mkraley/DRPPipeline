"""
Unit tests for inventory sheet updater factory.
"""

import sys
import unittest

from utils.Args import Args
from utils.Logger import Logger

from publisher.BaserowBatchSheetUpdater import BaserowBatchSheetUpdater
from publisher.GoogleSheetUpdater import GoogleSheetUpdater
from publisher.inventory_sheet_updater import (
    INVENTORY_SHEET_FORMAT_BASEROW_BATCH,
    INVENTORY_SHEET_FORMAT_DATA_INVENTORIES,
    get_inventory_sheet_updater,
)


class TestInventorySheetUpdaterFactory(unittest.TestCase):
    """Tests for get_inventory_sheet_updater."""

    def setUp(self) -> None:
        """Initialize Args for factory tests."""
        sys.argv = ["test", "publisher"]
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Reset Args."""
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}

    def test_default_returns_data_inventories_updater(self) -> None:
        """Default format is data inventories."""
        updater = get_inventory_sheet_updater()
        self.assertIsInstance(updater, GoogleSheetUpdater)

    def test_baserow_batch_format(self) -> None:
        """baserow_batch returns BaserowBatchSheetUpdater."""
        Args._config["inventory_sheet_format"] = INVENTORY_SHEET_FORMAT_BASEROW_BATCH
        updater = get_inventory_sheet_updater()
        self.assertIsInstance(updater, BaserowBatchSheetUpdater)

    def test_explicit_data_inventories(self) -> None:
        """Explicit data_inventories override works."""
        updater = get_inventory_sheet_updater(INVENTORY_SHEET_FORMAT_DATA_INVENTORIES)
        self.assertIsInstance(updater, GoogleSheetUpdater)

    def test_unknown_format_raises(self) -> None:
        """Unknown format names raise ValueError."""
        with self.assertRaises(ValueError):
            get_inventory_sheet_updater("unknown_format")
