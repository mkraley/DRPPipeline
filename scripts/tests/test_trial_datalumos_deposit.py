"""Unit tests for the deposit API trial script guards."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.trial_datalumos_deposit import project_is_ready, require_trial_drpid
from scripts.trial_elapsed import format_trial_elapsed


class TestTrialDatalumosDeposit(unittest.TestCase):
    """DRPID guard and the read-only contract."""

    def test_drpid_at_2500_is_refused(self) -> None:
        """Current batches stay on ids at or below 2500."""
        with self.assertRaises(ValueError):
            require_trial_drpid(2500)

    def test_drpid_above_2500_is_allowed(self) -> None:
        """An id above 2500 can be used for the trial."""
        require_trial_drpid(2501)

    def test_missing_summary_is_reported(self) -> None:
        """A row without a summary is refused before a browser opens."""
        message = project_is_ready({"title": "Has a title"}, 2600)
        self.assertIn("summary", message)

    def test_elapsed_line_includes_total_and_phases(self) -> None:
        """The summary line shows the whole run and each timed step."""
        text = format_trial_elapsed(
            82000,
            {"login": 18000, "workspace": 47000, "create": 1100},
        )
        self.assertEqual(
            text,
            "Elapsed 1m 22s (login 18.0s, workspace 47.0s, create 1.1s)",
        )

    def test_script_does_not_update_storage(self) -> None:
        """The trial must not write status or datalumos_id."""
        source = Path("scripts/trial_datalumos_deposit.py").read_text(encoding="utf-8")
        self.assertNotIn("update_record", source)


if __name__ == "__main__":
    unittest.main()
