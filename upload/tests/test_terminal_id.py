"""Unit tests for resolving the interactive shell process id."""

from __future__ import annotations

import unittest

from upload.terminal_id import resolve_terminal_id


class TestTerminalId(unittest.TestCase):
    """Prefer an explicit override, then a shell ancestor, then getppid."""

    def test_env_override_wins(self) -> None:
        """DRP_TERMINAL_ID pins the session file for this process."""
        terminal_id = resolve_terminal_id(
            getenv=lambda key: "99" if key == "DRP_TERMINAL_ID" else None,
            getppid=lambda: 1,
            parents=lambda: {},
        )
        self.assertEqual(terminal_id, 99)

    def test_nearest_shell_ancestor_is_used(self) -> None:
        """A launcher parent is skipped when a PowerShell ancestor exists."""
        tree = {
            10: (20, "python.exe"),
            20: (30, "conhost.exe"),
            30: (40, "powershell.exe"),
            40: (1, "explorer.exe"),
        }
        terminal_id = resolve_terminal_id(
            getenv=lambda _key: None,
            getppid=lambda: 20,
            parents=lambda: tree,
        )
        self.assertEqual(terminal_id, 30)

    def test_falls_back_to_parent_when_no_shell(self) -> None:
        """Unknown parents keep the previous getppid behavior."""
        terminal_id = resolve_terminal_id(
            getenv=lambda _key: None,
            getppid=lambda: 55,
            parents=lambda: {55: (1, "mystery.exe")},
        )
        self.assertEqual(terminal_id, 55)


if __name__ == "__main__":
    unittest.main()
