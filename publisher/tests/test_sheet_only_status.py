"""Unit tests for publisher.sheet_only_status helpers."""

import unittest

from publisher.sheet_only_status import (
    STATUS_UPDATED_COLLECTOR_HOLD,
    collector_hold_reason,
    is_collector_hold_status,
    resolve_sheet_only_config,
)


class TestSheetOnlyStatus(unittest.TestCase):
    """Tests for collector-hold and sheet-only status resolution."""

    def test_collector_hold_reason(self) -> None:
        self.assertEqual(
            collector_hold_reason("collector_hold - needs login"),
            "needs login",
        )
        self.assertEqual(
            collector_hold_reason("collector hold - needs script"),
            "needs script",
        )
        self.assertIsNone(collector_hold_reason("no_links"))
        self.assertIsNone(collector_hold_reason(None))

    def test_is_collector_hold_status(self) -> None:
        self.assertTrue(is_collector_hold_status("collector_hold - x"))
        self.assertFalse(is_collector_hold_status("sourced"))

    def test_resolve_preset_and_hold(self) -> None:
        self.assertEqual(
            resolve_sheet_only_config("no_links"),
            ("No live links", "updated_no_links", "N"),
        )
        self.assertEqual(
            resolve_sheet_only_config("collector_hold - needs login"),
            ("needs login", STATUS_UPDATED_COLLECTOR_HOLD, "?"),
        )
        self.assertIsNone(resolve_sheet_only_config("uploaded"))
