"""Tests for utils.drpid_list.parse_drpid_ids."""

import unittest

from utils.drpid_list import parse_drpid_ids


class TestParseDrpidIds(unittest.TestCase):
    """Unit tests for parse_drpid_ids."""

    def test_single_and_list(self) -> None:
        self.assertEqual(parse_drpid_ids("5"), [5])
        self.assertEqual(parse_drpid_ids("1,3,5"), [1, 3, 5])

    def test_range(self) -> None:
        self.assertEqual(parse_drpid_ids("5-7"), [5, 6, 7])
        self.assertEqual(parse_drpid_ids("1,3,5-8,20"), [1, 3, 5, 6, 7, 8, 20])

    def test_dedupes_and_sorts(self) -> None:
        self.assertEqual(parse_drpid_ids("7,5,5-6"), [5, 6, 7])

    def test_rejects_empty_and_invalid(self) -> None:
        with self.assertRaises(ValueError):
            parse_drpid_ids("")
        with self.assertRaises(ValueError):
            parse_drpid_ids("1,,2")
        with self.assertRaises(ValueError):
            parse_drpid_ids("abc")
        with self.assertRaises(ValueError):
            parse_drpid_ids("7-5")
        with self.assertRaises(ValueError):
            parse_drpid_ids("0")

    def test_flag_name_appears_in_errors(self) -> None:
        """Custom flag name is included in ValueError messages."""
        with self.assertRaises(ValueError) as ctx:
            parse_drpid_ids("", flag="--keep-ids")
        self.assertIn("--keep-ids", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
