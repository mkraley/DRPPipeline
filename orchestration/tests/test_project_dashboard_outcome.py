"""Tests for dashboard per-project outcome classification."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestration.Orchestrator import _project_dashboard_outcome


class TestProjectDashboardOutcome(unittest.TestCase):
    """Map Storage fields to scatter-plot colors."""

    @patch("orchestration.Orchestrator.Storage")
    def test_ok_when_clean(self, mock_storage: MagicMock) -> None:
        """Clean collected projects are green."""
        mock_storage.get.return_value = {
            "status": "collected",
            "errors": None,
            "warnings": None,
        }
        self.assertEqual(_project_dashboard_outcome(1), "ok")

    @patch("orchestration.Orchestrator.Storage")
    def test_error_from_errors_field(self, mock_storage: MagicMock) -> None:
        """Non-empty errors field is red."""
        mock_storage.get.return_value = {
            "status": "collected",
            "errors": "download failed",
            "warnings": None,
        }
        self.assertEqual(_project_dashboard_outcome(1), "error")

    @patch("orchestration.Orchestrator.Storage")
    def test_error_from_error_status(self, mock_storage: MagicMock) -> None:
        """*-error status is red even if errors text was cleared."""
        mock_storage.get.return_value = {
            "status": "sourced-error",
            "errors": "",
            "warnings": "",
        }
        self.assertEqual(_project_dashboard_outcome(1), "error")

    @patch("orchestration.Orchestrator.Storage")
    def test_warning_from_warnings_field(self, mock_storage: MagicMock) -> None:
        """Non-empty warnings field is yellow when there is no error."""
        mock_storage.get.return_value = {
            "status": "collected",
            "errors": "",
            "warnings": "low-confidence geo",
        }
        self.assertEqual(_project_dashboard_outcome(1), "warning")


if __name__ == "__main__":
    unittest.main()
