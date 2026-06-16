"""Tests for utils.inventory_sheet_reconcile."""

import unittest

from utils.inventory_sheet_reconcile import (
    ReconcileAction,
    classify_reconcile_actions,
    titles_match,
)


class TestInventorySheetReconcile(unittest.TestCase):
    def test_classify_ok_when_url_and_datalumos_match(self) -> None:
        actions = classify_reconcile_actions(
            [
                {
                    "DRPID": 1,
                    "source_url": "https://example.com/a",
                    "datalumos_id": "248721",
                    "title": "My Dataset",
                }
            ],
            [
                {
                    "URL": "https://example.com/a",
                    "Download Location": "https://www.datalumos.org/datalumos/project/248721/version/V1/view",
                    "Title": "My Dataset",
                }
            ],
        )
        self.assertEqual(actions[0].action, "ok")

    def test_classify_fix_when_datalumos_differs(self) -> None:
        actions = classify_reconcile_actions(
            [
                {
                    "DRPID": 29,
                    "source_url": "https://example.com/RDS-2022-0015-4",
                    "datalumos_id": "248721",
                    "title": "Wildfire",
                }
            ],
            [
                {
                    "URL": "https://example.com/RDS-2022-0015-4",
                    "Download Location": "https://www.datalumos.org/datalumos/project/249000/version/V1/view",
                    "Title": "Wildfire",
                }
            ],
        )
        self.assertEqual(actions[0].action, "fix")
        self.assertEqual(actions[0].sheet_datalumos_id, "249000")

    def test_classify_append_when_exact_url_missing(self) -> None:
        actions = classify_reconcile_actions(
            [
                {
                    "DRPID": 307,
                    "source_url": "https://example.com/RDS-2022-0015",
                    "datalumos_id": "249000",
                    "title": "Wildfire",
                }
            ],
            [
                {
                    "URL": "https://example.com/RDS-2022-0015-4",
                    "Download Location": "https://www.datalumos.org/datalumos/project/248721/version/V1/view",
                }
            ],
        )
        self.assertEqual(actions[0].action, "append")

    def test_classify_skip_when_db_incomplete(self) -> None:
        actions = classify_reconcile_actions(
            [{"DRPID": 5, "source_url": "", "datalumos_id": "1", "title": ""}],
            [],
        )
        self.assertEqual(actions[0].action, "skip")

    def test_titles_match_ignores_case_and_whitespace(self) -> None:
        self.assertTrue(titles_match("  Hello   World ", "hello world"))


if __name__ == "__main__":
    unittest.main()
