"""Tests for scripts.update_datalumos_titles helpers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from scripts.update_datalumos_titles import (
    ELIGIBLE_STATUSES,
    project_url,
    select_eligible_projects,
)


class TestUpdateDatalumosTitles(unittest.TestCase):
    """Unit tests for DataLumos title-update script helpers."""

    def test_project_url(self) -> None:
        """Workspace URL includes goToPath for the project id."""
        url = project_url("252293")
        self.assertIn("252293", url)
        self.assertIn("goToLevel=project", url)

    def test_select_eligible_projects_filters(self) -> None:
        """Only uploaded statuses with datalumos_id and title are kept."""
        storage = MagicMock()
        storage.get.side_effect = lambda drpid: {
            1: {
                "DRPID": 1,
                "status": "uploaded",
                "datalumos_id": "111",
                "title": "A — B",
            },
            2: {
                "DRPID": 2,
                "status": "collected",
                "datalumos_id": "222",
                "title": "Nope",
            },
            3: {
                "DRPID": 3,
                "status": "uploaded - large file",
                "datalumos_id": "333",
                "title": "Large",
            },
            4: None,
            5: {
                "DRPID": 5,
                "status": "uploaded",
                "datalumos_id": "",
                "title": "Missing id",
            },
        }.get(drpid)

        projects, skips = select_eligible_projects(storage, [1, 2, 3, 4, 5])
        self.assertEqual([p["DRPID"] for p in projects], [1, 3])
        self.assertEqual(len(skips), 3)
        self.assertTrue(any("not in storage" in s for s in skips))
        self.assertTrue(any("collected" in s for s in skips))
        self.assertTrue(any("datalumos_id" in s for s in skips))
        self.assertIn("uploaded", ELIGIBLE_STATUSES)
        self.assertIn("uploaded - large file", ELIGIBLE_STATUSES)


if __name__ == "__main__":
    unittest.main()
