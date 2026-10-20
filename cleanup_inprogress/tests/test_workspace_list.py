"""Tests for DataLumos workspace sidebar parsing."""

import unittest

from cleanup_inprogress.workspace_list import (
    is_published_entry,
    project_url,
    unpublished_workspace_ids,
    workspace_id_from_entry,
)


class TestWorkspaceList(unittest.TestCase):
    """Parse sidebar labels into ids and published vs in-progress."""

    def test_id_from_datalumos_label(self) -> None:
        """The numeric id is taken from datalumos-<id> in the label."""
        self.assertEqual(
            workspace_id_from_entry("Park roads\ndatalumos-256149"),
            "256149",
        )

    def test_id_from_href_when_label_has_none(self) -> None:
        """A /datalumos/<id> href supplies the id when the label does not."""
        self.assertEqual(
            workspace_id_from_entry("Park roads", "/datalumos/256149"),
            "256149",
        )

    def test_missing_id(self) -> None:
        """Labels with no project id return None."""
        self.assertIsNone(workspace_id_from_entry("Workspace", ""))

    def test_published_mark(self) -> None:
        """(Published) marks a finished project; other labels do not."""
        self.assertTrue(is_published_entry("Park roads (Published)\ndatalumos-1"))
        self.assertFalse(is_published_entry("Park roads\ndatalumos-2"))

    def test_project_url(self) -> None:
        """Direct project URLs include goToPath and goToLevel."""
        url = project_url("256149")
        self.assertIn("goToPath=/datalumos/256149", url)
        self.assertIn("goToLevel=project", url)

    def test_unpublished_ids_skip_published_and_non_projects(self) -> None:
        """Sidebar HTML yields only project ids that lack (Published)."""
        html = (
            '<ul class="list-group">'
            '<li><a style="color:inherit;">Workspace</a></li>'
            '<li><a href="#">datalumos-255475 (Published)</a></li>'
            '<li><a href="#">datalumos-255551</a></li>'
            '<li><a style="color:inherit;">Shared with me</a></li>'
            "</ul>"
        )
        self.assertEqual(unpublished_workspace_ids(html), ["255551"])
