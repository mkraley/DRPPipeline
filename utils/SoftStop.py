"""Stop an orchestrator batch after the current project, or immediately."""

from __future__ import annotations

import signal
import sys
import threading
from contextlib import contextmanager
from typing import Callable, Iterator


class SoftStop:
    """
    Turn the first Ctrl-C into a request to stop after the current project.

    A second Ctrl-C while that request is waiting raises ``KeyboardInterrupt``,
    which aborts the project the way a single Ctrl-C did before.
    """

    _requested = threading.Event()
    _active = False
    _installed = 0
    _previous: signal.Handlers | None = None
    _callbacks: list[Callable[[], None]] = []
    _callback_lock = threading.Lock()

    @classmethod
    def install(cls) -> None:
        """Install the Ctrl-C handler, remembering the previous one."""
        if cls._installed == 0:
            cls._previous = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, cls.handle)
        cls._installed += 1

    @classmethod
    def restore(cls) -> None:
        """Put back the Ctrl-C handler captured by :meth:`install`."""
        if cls._installed == 0:
            return
        cls._installed -= 1
        if cls._installed > 0:
            return
        cls._active = False
        cls._requested.clear()
        if cls._previous is not None:
            signal.signal(signal.SIGINT, cls._previous)
            cls._previous = None

    @classmethod
    @contextmanager
    def scope(cls) -> Iterator[None]:
        """
        Arm soft stop for a project loop.

        Outside this scope, Ctrl-C still interrupts immediately.
        """
        cls._requested.clear()
        cls._active = True
        try:
            yield
        finally:
            cls._active = False
            cls._requested.clear()

    @classmethod
    def requested(cls) -> bool:
        """Return True after Ctrl-C asked to stop at the next project boundary."""
        return cls._requested.is_set()

    @classmethod
    def handle(cls, signum: int, frame: object | None) -> None:
        """
        Handle Ctrl-C.

        The first press while :meth:`scope` is active sets the stop flag.
        Another press, or a press outside that scope, raises ``KeyboardInterrupt``.
        """
        if cls._active and not cls._requested.is_set():
            cls._requested.set()
            cls._write_notice()
            return
        cls._run_immediate_callbacks()
        signal.signal(signal.SIGINT, signal.default_int_handler)
        raise KeyboardInterrupt

    @classmethod
    @contextmanager
    def on_immediate_stop(cls, callback: Callable[[], None]) -> Iterator[None]:
        """
        Run ``callback`` when Ctrl-C aborts the current project.

        Used so a child process that ignores the console Ctrl-C event can
        still be stopped by the second press.
        """
        with cls._callback_lock:
            cls._callbacks.append(callback)
        try:
            yield
        finally:
            with cls._callback_lock:
                cls._remove_callback(callback)

    @classmethod
    def _remove_callback(cls, callback: Callable[[], None]) -> None:
        """Drop one immediate-stop callback if it is still registered."""
        try:
            cls._callbacks.remove(callback)
        except ValueError:
            return

    @classmethod
    def _run_immediate_callbacks(cls) -> None:
        """Run registered immediate-stop callbacks, ignoring their errors."""
        with cls._callback_lock:
            callbacks = list(cls._callbacks)
        for callback in callbacks:
            try:
                callback()
            except Exception:
                continue

    @staticmethod
    def _write_notice() -> None:
        """Tell the operator the batch will stop after this project."""
        message = (
            "Ctrl-C — will stop after the current project finishes. "
            "Press Ctrl-C again to stop now.\n"
        )
        try:
            sys.stderr.write(message)
            sys.stderr.flush()
        except Exception:
            return
