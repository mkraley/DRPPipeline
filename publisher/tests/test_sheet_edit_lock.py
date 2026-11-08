"""Tests for the cross-process Google Sheet edit lock."""

from __future__ import annotations

import sys
import threading
import time
import unittest

from publisher.sheet_edit_lock import SheetEditLock
from utils.Args import Args
from utils.Logger import Logger


class TestSheetEditLock(unittest.TestCase):
    """One editor at a time for a spreadsheet tab."""

    def setUp(self) -> None:
        """Point the lock file at the pytest database directory."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "publish"]
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore the process command line."""
        sys.argv = self._original_argv

    def test_second_editor_waits_until_the_first_releases(self) -> None:
        """A second lock stays outside the sheet until the first editor leaves."""
        first = SheetEditLock("sheet-a", "Inventory")
        first.__enter__()
        waited: list[bool] = []
        entered = threading.Event()

        def wait_for_sheet() -> None:
            entered.set()
            with SheetEditLock("sheet-a", "Inventory") as lock:
                waited.append(lock.waited)

        waiter = threading.Thread(target=wait_for_sheet, daemon=True)
        waiter.start()
        self.assertTrue(entered.wait(5))
        time.sleep(0.3)
        self.assertTrue(waiter.is_alive())
        self.assertEqual(waited, [])
        first.__exit__(None, None, None)
        waiter.join(5)
        self.assertFalse(waiter.is_alive())
        self.assertEqual(waited, [True])

    def test_different_sheets_do_not_block_each_other(self) -> None:
        """A lock for another spreadsheet is acquired immediately."""
        with SheetEditLock("sheet-a", "Inventory"):
            with SheetEditLock("sheet-b", "Inventory") as other:
                self.assertFalse(other.waited)


if __name__ == "__main__":
    unittest.main()
