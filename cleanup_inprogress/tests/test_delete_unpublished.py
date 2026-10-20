"""Tests for successive deletion of unpublished DataLumos projects."""

import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from cleanup_inprogress.delete_queue import (
    SKIP_UNDELETABLE_IDS,
    append_result,
    delete_projects,
    deletion_targets,
    load_workspace_ids,
    successful_ids,
)
from cleanup_inprogress.delete_tally import DeleteTally
from cleanup_inprogress.sidebar_project_deleter import (
    CONFIRM_BUTTON,
    DELETE_ITEM,
    MORE_BUTTON,
    SidebarProjectDeleter,
)
from utils.Logger import Logger


class TestDeleteQueue(unittest.TestCase):
    """Filter the unpublished list and tally each delete."""

    def setUp(self) -> None:
        """Quiet the logger used by the delete loop."""
        Logger.initialize(log_level="ERROR")

    def test_skip_undeletable_ids(self) -> None:
        """The four Unpublished projects are not deletion targets."""
        ids = ["255551", "255552", "255562", "255566", "256000", "257664"]
        self.assertEqual(deletion_targets(ids), ["256000", "257664"])
        self.assertEqual(
            SKIP_UNDELETABLE_IDS,
            ("255551", "255552", "255562", "255566"),
        )

    def test_load_csv_and_resume(self) -> None:
        """A prior success is skipped when the same CSV is run again."""
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "projects.csv"
            log_path = root / "results.csv"
            self._write_ids(source, ["256000", "256132", "255551"])
            append_result(log_path, "256000", "success", "deleted")
            targets = deletion_targets(
                load_workspace_ids(source),
                already_deleted=successful_ids(log_path),
            )
            self.assertEqual(targets, ["256132"])

    def test_failure_does_not_stop_the_rest(self) -> None:
        """One failed delete is logged and the next id is still attempted."""
        with TemporaryDirectory() as folder:
            log_path = Path(folder) / "results.csv"

            def delete_one(workspace_id: str) -> tuple[bool, str]:
                if workspace_id == "256132":
                    raise RuntimeError("menu missing")
                return True, "deleted"

            tally = delete_projects(["256000", "256132", "256135"], delete_one, log_path)
            self.assertEqual(tally.success_count, 2)
            self.assertEqual(tally.failure_count, 1)
            self.assertEqual(tally.failures[0], ("256132", "menu missing"))
            self.assertIn("successes=2 failures=1", tally.summary())
            rows = list(csv.DictReader(log_path.open(encoding="utf-8-sig")))
            self.assertEqual([row["outcome"] for row in rows], ["success", "failure", "success"])

    def test_tally_records_each_outcome(self) -> None:
        """Success and failure lists stay in attempt order."""
        tally = DeleteTally()
        tally.record_success("256000")
        tally.record_failure("256132", "Delete Project is disabled")
        self.assertEqual(tally.successes, ["256000"])
        self.assertEqual(tally.success_count, 1)
        self.assertEqual(tally.failure_count, 1)

    def _write_ids(self, path: Path, workspace_ids: list[str]) -> None:
        """Write a workspace_id CSV using the same encoding as the parser."""
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["workspace_id", "url"])
            for workspace_id in workspace_ids:
                writer.writerow([workspace_id, "https://example.test/" + workspace_id])


class TestSidebarProjectDeleter(unittest.TestCase):
    """More-menu delete uses the direct project page, not the workspace list."""

    def test_delete_one_confirms(self) -> None:
        """A enabled Delete Project item is clicked and then confirmed."""
        page = self._page(delete_class="")
        ok, detail = SidebarProjectDeleter(page).delete_one("256000")
        self.assertTrue(ok)
        self.assertEqual(detail, "deleted")
        page.goto.assert_called_once()
        self.assertIn("goToPath=/datalumos/256000", page.goto.call_args.args[0])
        self.assertEqual(page.goto.call_args.kwargs["wait_until"], "commit")

    def test_delete_one_disabled(self) -> None:
        """A disabled Delete Project item is a failure and is not confirmed."""
        page = self._page(delete_class="disabled")
        ok, detail = SidebarProjectDeleter(page).delete_one("255551")
        self.assertFalse(ok)
        self.assertEqual(detail, "Delete Project is disabled")
        page.locator(CONFIRM_BUTTON).first.click.assert_not_called()

    def _page(self, delete_class: str) -> MagicMock:
        """Return a page whose locators answer the delete sequence."""
        page = MagicMock()
        more = MagicMock()
        more.count.return_value = 1
        delete_item = MagicMock()
        delete_item.count.return_value = 1
        delete_item.first.get_attribute.return_value = delete_class
        confirm = MagicMock()

        def locator(selector: str) -> MagicMock:
            if selector == MORE_BUTTON:
                return more
            if selector == DELETE_ITEM:
                return delete_item
            if selector == CONFIRM_BUTTON:
                return confirm
            raise AssertionError(selector)

        page.locator.side_effect = locator
        cdp = MagicMock()
        cdp.send.return_value = {"result": {"value": "ready"}}
        page.context.new_cdp_session.return_value = cdp
        return page
