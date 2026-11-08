"""Unit tests for the per-terminal DataLumos session file."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from upload.terminal_deposit_store import TerminalDepositStore


class TestTerminalDepositStore(unittest.TestCase):
    """One terminal can reload its token. Another terminal cannot."""

    def setUp(self) -> None:
        """Use a private folder so the test does not touch a real session."""
        self._folder = Path(tempfile.mkdtemp())

    def test_round_trip_keeps_the_token_and_cookies(self) -> None:
        """A saved session loads back for the same terminal id."""
        store = TerminalDepositStore(self._folder, terminal_id=10)
        store.save("jwt-1", {"cookies": [{"name": "JSESSIONID"}], "origins": []})
        token, state = store.load()
        self.assertEqual(token, "jwt-1")
        self.assertEqual(state["cookies"][0]["name"], "JSESSIONID")

    def test_another_terminal_does_not_see_the_session(self) -> None:
        """A different shell process id loads an empty session."""
        TerminalDepositStore(self._folder, terminal_id=10).save("jwt-1", None)
        token, state = TerminalDepositStore(self._folder, terminal_id=11).load()
        self.assertEqual(token, "")
        self.assertIsNone(state)

    def test_delete_removes_the_session(self) -> None:
        """A rejected login removes the file for this terminal only."""
        first = TerminalDepositStore(self._folder, terminal_id=10)
        second = TerminalDepositStore(self._folder, terminal_id=11)
        first.save("jwt-1", None)
        second.save("jwt-2", None)
        first.delete()
        self.assertEqual(first.load()[0], "")
        self.assertEqual(second.load()[0], "jwt-2")
