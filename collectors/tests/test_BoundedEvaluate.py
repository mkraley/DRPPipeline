"""Tests for BoundedEvaluate."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock

from collectors.BoundedEvaluate import evaluate_with_timeout, query_count_with_timeout


class TestBoundedEvaluate(unittest.TestCase):
    """A page script either uses the Playwright deadline or the test double."""

    def test_mock_page_uses_evaluate(self) -> None:
        """A test double keeps calling ``page.evaluate``."""
        page = MagicMock()
        page.evaluate.return_value = 3
        self.assertEqual(evaluate_with_timeout(page, "() => 1", 2), 3)
        page.evaluate.assert_called_once_with("() => 1", 2)

    def test_real_page_sends_a_timeout(self) -> None:
        """A Playwright page gives the script a deadline."""
        page = MagicMock()

        async def send(
            method: str,
            timeout_calculator: object,
            params: dict[str, object] | None = None,
        ) -> dict[str, object]:
            self.assertEqual(method, "evaluateExpression")
            assert callable(timeout_calculator)
            self.assertEqual(timeout_calculator(None), 20000)
            assert params is not None
            self.assertEqual(params["expression"], "() => 4")
            return {"v": 4}

        page.main_frame._impl_obj._channel.send = send
        page._sync = lambda coro: asyncio.run(coro)
        self.assertEqual(evaluate_with_timeout(page, "() => 4"), 4)
        page.evaluate.assert_not_called()

    def test_count_uses_a_timeout(self) -> None:
        """A Playwright locator gives the element count a deadline."""
        locator = MagicMock()

        async def send(
            method: str,
            timeout_calculator: object,
            params: dict[str, object] | None = None,
        ) -> int:
            self.assertEqual(method, "queryCount")
            assert callable(timeout_calculator)
            self.assertEqual(timeout_calculator(None), 5000)
            assert params is not None
            self.assertEqual(params["selector"], "button.more-button")
            return 2

        locator._impl_obj._frame._channel.send = send
        locator._impl_obj._selector = "button.more-button"
        locator.page._sync = lambda coro: asyncio.run(coro)
        self.assertEqual(query_count_with_timeout(locator), 2)
        locator.count.assert_not_called()


if __name__ == "__main__":
    unittest.main()
