"""Unit tests for utils.windows_process."""

from __future__ import annotations

import os
import sys
import unittest

from utils.windows_process import pid_alive, terminal_pid


class TestWindowsProcess(unittest.TestCase):
    """PID liveness and terminal parent lookup."""

    def test_pid_alive_current_process(self) -> None:
        """The current interpreter PID is alive."""
        self.assertTrue(pid_alive(os.getpid()))

    def test_pid_alive_rejects_bogus(self) -> None:
        """A clearly invalid PID is not alive."""
        self.assertFalse(pid_alive(0))
        self.assertFalse(pid_alive(-1))
        self.assertFalse(pid_alive(999999001))

    @unittest.skipUnless(sys.platform == "win32", "Windows-only parent walk")
    def test_terminal_pid_walks_to_shell_or_none(self) -> None:
        """terminal_pid returns an int or None without raising."""
        result = terminal_pid(os.getpid())
        self.assertTrue(result is None or isinstance(result, int))
