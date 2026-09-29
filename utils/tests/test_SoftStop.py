"""Tests for the Ctrl-C soft stop handler."""

import signal
import unittest
from unittest.mock import MagicMock

from utils.SoftStop import SoftStop


class TestSoftStop(unittest.TestCase):
    """First Ctrl-C waits for the current project; the next one interrupts."""

    def tearDown(self) -> None:
        """Leave the process Ctrl-C handler as the test found it."""
        while SoftStop._installed:
            SoftStop.restore()

    def test_install_and_restore_round_trip(self) -> None:
        previous = signal.getsignal(signal.SIGINT)
        SoftStop.install()
        installed = signal.getsignal(signal.SIGINT)
        self.assertIs(getattr(installed, "__func__", None), SoftStop.handle.__func__)
        SoftStop.restore()
        self.assertIs(signal.getsignal(signal.SIGINT), previous)
        self.assertFalse(SoftStop.requested())

    def test_first_ctrl_c_in_scope_sets_flag(self) -> None:
        with SoftStop.scope():
            SoftStop.handle(signal.SIGINT, None)
            self.assertTrue(SoftStop.requested())
        self.assertFalse(SoftStop.requested())

    def test_second_ctrl_c_raises_and_runs_callback(self) -> None:
        previous = signal.getsignal(signal.SIGINT)
        callback = MagicMock()
        try:
            with SoftStop.scope():
                with SoftStop.on_immediate_stop(callback):
                    SoftStop.handle(signal.SIGINT, None)
                    callback.assert_not_called()
                    with self.assertRaises(KeyboardInterrupt):
                        SoftStop.handle(signal.SIGINT, None)
            callback.assert_called_once()
        finally:
            signal.signal(signal.SIGINT, previous)

    def test_ctrl_c_outside_scope_interrupts_immediately(self) -> None:
        previous = signal.getsignal(signal.SIGINT)
        try:
            with self.assertRaises(KeyboardInterrupt):
                SoftStop.handle(signal.SIGINT, None)
            self.assertFalse(SoftStop.requested())
        finally:
            signal.signal(signal.SIGINT, previous)


if __name__ == "__main__":
    unittest.main()
