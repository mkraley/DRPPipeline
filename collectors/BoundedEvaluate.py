"""Run a page script with a deadline.

Playwright's ``page.evaluate`` sends no timeout. A Hub page that never
finishes loading leaves that call waiting until the browser is closed.
"""

from __future__ import annotations

import inspect
from typing import Any

_SCRIPT_TIMEOUT_MS = 20000


def evaluate_with_timeout(
    page: Any,
    expression: str,
    arg: Any = None,
    timeout_ms: int = _SCRIPT_TIMEOUT_MS,
) -> Any:
    """Evaluate ``expression`` and give up after ``timeout_ms``.

    A test double falls back to ``page.evaluate``.

    Args:
        page: Playwright page.
        expression: JavaScript function or expression.
        arg: Optional value passed to the function.
        timeout_ms: Deadline for the script.

    Returns:
        The value the script returned.
    """
    if not _script_accepts_timeout(page):
        if arg is None:
            return page.evaluate(expression)
        return page.evaluate(expression, arg)
    from playwright._impl._js_handle import parse_result, serialize_argument

    encoded = page._sync(
        page.main_frame._impl_obj._channel.send(
            "evaluateExpression",
            lambda _timeout: timeout_ms,
            {"expression": expression, "arg": serialize_argument(arg)},
        )
    )
    return parse_result(encoded)


def query_count_with_timeout(locator: Any, timeout_ms: int = 5000) -> int:
    """Count matching elements, giving up after ``timeout_ms``.

    ``locator.count`` sends no timeout. A page that is still loading leaves
    that call waiting.

    Args:
        locator: Playwright locator.
        timeout_ms: Deadline for the count.

    Returns:
        A non-negative count, or 0 when the count cannot be made.
    """
    impl = getattr(locator, "_impl_obj", None)
    frame = getattr(impl, "_frame", None)
    selector = getattr(impl, "_selector", None)
    page = getattr(locator, "page", None)
    send = getattr(getattr(frame, "_channel", None), "send", None)
    runner = getattr(page, "_sync", None)
    real = (
        isinstance(selector, str)
        and inspect.iscoroutinefunction(send)
        and callable(runner)
    )
    if not real:
        return _plain_count(locator)
    if "internal:" in selector or ">>" in selector:
        return 0
    if _script_accepts_timeout(page):
        try:
            found = evaluate_with_timeout(
                page,
                "(selector) => document.querySelectorAll(selector).length",
                selector,
                timeout_ms,
            )
            return max(int(found or 0), 0)
        except Exception:
            return 0
    try:
        return max(int(runner(send(
            "queryCount",
            lambda _timeout: timeout_ms,
            {"selector": selector},
        ))), 0)
    except Exception:
        return 0


def _plain_count(locator: Any) -> int:
    """Return ``locator.count()``, or 0 when that call fails."""
    try:
        return max(int(locator.count()), 0)
    except Exception:
        return 0


def _script_accepts_timeout(page: Any) -> bool:
    """Return True when ``page`` is a real Playwright page."""
    frame = getattr(getattr(page, "main_frame", None), "_impl_obj", None)
    send = getattr(getattr(frame, "_channel", None), "send", None)
    return inspect.iscoroutinefunction(send) and callable(getattr(page, "_sync", None))
