"""
Unit tests for utils.Logging helpers.
"""

import unittest
from unittest.mock import Mock, patch

from utils.Logging import record_fatal_error


class TestLogging(unittest.TestCase):
    """Test cases for utils.Logging."""

    @patch("utils.Logging.Logger")
    @patch("utils.Logging.Storage")
    def test_record_fatal_error_updates_storage(self, mock_storage: Mock, mock_logger: Mock) -> None:
        """record_fatal_error(update_storage=True) sets status and appends error."""
        record_fatal_error(123, "boom", update_storage=True)

        mock_logger.error.assert_called_once_with("boom")
        mock_storage.update_record.assert_called_once_with(123, {"status": "Error"})
        mock_storage.append_to_field.assert_called_once_with(123, "errors", "boom")

    @patch("utils.Logging.Logger")
    @patch("utils.Logging.Storage")
    def test_record_fatal_error_no_storage(self, mock_storage: Mock, mock_logger: Mock) -> None:
        """record_fatal_error(update_storage=False) only logs."""
        record_fatal_error(123, "nope", update_storage=False)

        mock_logger.error.assert_called_once_with("nope")
        mock_storage.update_record.assert_not_called()
        mock_storage.append_to_field.assert_not_called()

