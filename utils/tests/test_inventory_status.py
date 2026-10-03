"""Tests for collected size classification."""

from __future__ import annotations

import unittest

from utils.inventory_status import (
    MAX_COLLECTED_BYTES,
    XLARGE_MIN_BYTES,
    classify_collected_status,
    upload_status_for_collected,
)


class TestInventoryStatus(unittest.TestCase):
    """Size cutoffs are 1 GiB exclusive and 25 GiB inclusive."""

    def test_exact_one_gib_stays_collected(self) -> None:
        """A project of exactly 1 GiB is not large."""
        self.assertEqual(
            classify_collected_status(MAX_COLLECTED_BYTES, has_unknown_size=False),
            "collected",
        )

    def test_over_one_gib_is_large(self) -> None:
        """Totals between 1 GiB and 25 GiB are large."""
        self.assertEqual(
            classify_collected_status(MAX_COLLECTED_BYTES + 1, has_unknown_size=False),
            "collected - large",
        )

    def test_exact_25_gib_is_xlarge(self) -> None:
        """25 GiB and above is xlarge."""
        self.assertEqual(
            classify_collected_status(XLARGE_MIN_BYTES, has_unknown_size=False),
            "collected - xlarge",
        )

    def test_unknown_size_below_25_gib_is_xlarge(self) -> None:
        """An unknown size cannot resume until an operator resizes the project."""
        self.assertEqual(
            classify_collected_status(100, has_unknown_size=True),
            "collected - xlarge",
        )

    def test_upload_status_follows_collected_class(self) -> None:
        """The first upload keeps the size class in the status name."""
        self.assertEqual(upload_status_for_collected("collected - large"), "uploaded - large")
        self.assertEqual(upload_status_for_collected("collected - xlarge"), "uploaded - xlarge")
        self.assertEqual(upload_status_for_collected("collected"), "uploaded")
