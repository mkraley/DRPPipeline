"""Tests for DataLumos data type normalization."""

from __future__ import annotations

import unittest

from utils.datalumos_data_types import (
    DATA_TYPE_GIS,
    DATA_TYPE_OBSERVATIONAL,
    normalize_datalumos_data_types,
)


class TestDatalumosDataTypes(unittest.TestCase):
    """Tests for kindOfData label normalization."""

    def test_normalize_canonical_labels(self) -> None:
        """Canonical labels pass through unchanged."""
        result = normalize_datalumos_data_types(
            "Observational data; Geographic information system (GIS) data"
        )
        self.assertEqual(
            result,
            ["Observational data", DATA_TYPE_GIS],
        )

    def test_normalize_short_aliases(self) -> None:
        """Collector shorthand aliases map to DataLumos labels."""
        result = normalize_datalumos_data_types("GIS; tabular")
        self.assertEqual(result, [DATA_TYPE_GIS, DATA_TYPE_OBSERVATIONAL])

    def test_normalize_ignores_unknown_tokens(self) -> None:
        """Unknown tokens are dropped."""
        result = normalize_datalumos_data_types("GIS; other; not-a-real-type")
        self.assertEqual(result, [DATA_TYPE_GIS])


if __name__ == "__main__":
    unittest.main()
