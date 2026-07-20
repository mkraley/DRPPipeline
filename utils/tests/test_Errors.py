"""
Unit tests for utils.Errors helpers.
"""

import unittest
from unittest.mock import Mock, patch

from utils.Errors import (
    derive_error_status,
    is_error_status,
    normalize_status_hyphens,
    record_crash,
    record_error,
    record_warning,
)

# Module-level mocks for patch decorators (must be defined before use in decorators)
_mock_storage = Mock()
_mock_logger = Mock()


class TestRecordCrash(unittest.TestCase):
    """Test record_crash."""

    @patch("utils.Errors.Logger", Mock())
    def test_record_crash_logs_and_raises(self) -> None:
        """record_crash logs at exception level and raises RuntimeError."""
        with self.assertRaises(RuntimeError) as ctx:
            record_crash("fatal")
        self.assertEqual(str(ctx.exception), "fatal")


class TestNormalizeStatusHyphens(unittest.TestCase):
    """Test normalize_status_hyphens."""

    def test_collapses_spaced_hyphens_and_spaces(self) -> None:
        self.assertEqual(
            normalize_status_hyphens("uploaded - large file"),
            "uploaded-large-file",
        )
        self.assertEqual(
            normalize_status_hyphens("  sourced  -  error  "),
            "sourced-error",
        )


class TestIsErrorStatus(unittest.TestCase):
    """Test is_error_status."""

    def test_compact_and_spaced_forms(self) -> None:
        self.assertTrue(is_error_status("error"))
        self.assertTrue(is_error_status("sourced-error"))
        self.assertTrue(is_error_status("sourced - error"))
        self.assertTrue(is_error_status("uploaded - large file - error"))
        self.assertTrue(is_error_status("uploaded - large file-error"))
        self.assertFalse(is_error_status("sourced"))
        self.assertFalse(is_error_status("uploaded - large file"))
        self.assertFalse(is_error_status(None))
        self.assertFalse(is_error_status(""))


class TestDeriveErrorStatus(unittest.TestCase):
    """Test derive_error_status."""

    def test_from_sourced(self) -> None:
        self.assertEqual(derive_error_status("sourced"), "sourced-error")

    def test_from_spaced_status_uses_compact_form(self) -> None:
        self.assertEqual(
            derive_error_status("uploaded - large file"),
            "uploaded-large-file-error",
        )
        self.assertEqual(
            derive_error_status("collected - external archive"),
            "collected-external-archive-error",
        )

    def test_empty_becomes_error(self) -> None:
        self.assertEqual(derive_error_status(None), "error")
        self.assertEqual(derive_error_status(""), "error")

    def test_already_error_normalized(self) -> None:
        self.assertEqual(derive_error_status("error"), "error")
        self.assertEqual(derive_error_status("sourced-error"), "sourced-error")
        self.assertEqual(derive_error_status("sourced - error"), "sourced-error")
        self.assertEqual(
            derive_error_status("uploaded - large file - error"),
            "uploaded-large-file-error",
        )
        self.assertEqual(
            derive_error_status("uploaded - large file-error"),
            "uploaded-large-file-error",
        )


class TestRecordError(unittest.TestCase):
    """Test record_error."""

    @patch("utils.Errors.Storage", _mock_storage)
    @patch("utils.Errors.Logger", _mock_logger)
    def test_record_error_updates_storage(self) -> None:
        """record_error(update_storage=True) sets status from previous status and appends error."""
        _mock_storage.reset_mock()
        _mock_logger.reset_mock()
        _mock_storage.get.return_value = {"status": "sourced"}
        record_error(123, "boom", update_storage=True)

        _mock_logger.error.assert_called_once_with("boom")
        _mock_storage.get.assert_called_once_with(123)
        _mock_storage.update_record.assert_called_once_with(123, {"status": "sourced-error"})
        _mock_storage.append_to_field.assert_called_once_with(123, "errors", "boom")

    @patch("utils.Errors.Storage", _mock_storage)
    @patch("utils.Errors.Logger", _mock_logger)
    def test_record_error_normalizes_spaced_previous_status(self) -> None:
        """Spaced base statuses become compact xxx-error."""
        _mock_storage.reset_mock()
        _mock_logger.reset_mock()
        _mock_storage.get.return_value = {"status": "uploaded - large file"}
        record_error(5, "fail", update_storage=True)
        _mock_storage.update_record.assert_called_once_with(
            5, {"status": "uploaded-large-file-error"}
        )

    @patch("utils.Errors.Logger", _mock_logger)
    @patch("utils.Errors.Storage", _mock_storage)
    def test_record_error_no_storage(self) -> None:
        """record_error(update_storage=False) only logs."""
        _mock_storage.reset_mock()
        _mock_logger.reset_mock()
        record_error(123, "nope", update_storage=False)

        _mock_logger.error.assert_called_once_with("nope")
        _mock_storage.update_record.assert_not_called()
        _mock_storage.append_to_field.assert_not_called()

    @patch("utils.Errors.Logger", new_callable=Mock)
    @patch("utils.Errors.Storage", new_callable=Mock)
    def test_record_error_custom_status(self, mock_storage: Mock, mock_logger: Mock) -> None:
        """record_error uses status_value when provided."""
        record_error(99, "bad", update_storage=True, status_value="failed")

        mock_storage.update_record.assert_called_once_with(99, {"status": "failed"})

    @patch("utils.Errors.Logger", new_callable=Mock)
    @patch("utils.Errors.Storage", new_callable=Mock)
    def test_record_error_normalizes_custom_spaced_error_status(
        self, mock_storage: Mock, mock_logger: Mock
    ) -> None:
        """Custom spaced error status_value is normalized to compact form."""
        record_error(99, "bad", update_storage=True, status_value="sourced - error")
        mock_storage.update_record.assert_called_once_with(
            99, {"status": "sourced-error"}
        )


class TestRecordWarning(unittest.TestCase):
    """Test record_warning."""

    @patch("utils.Errors.Storage", _mock_storage)
    @patch("utils.Errors.Logger", _mock_logger)
    def test_record_warning_updates_storage(self) -> None:
        """record_warning(update_storage=True) logs and appends to warnings."""
        _mock_logger.reset_mock()
        _mock_storage.reset_mock()
        record_warning(123, "careful", update_storage=True)

        _mock_logger.warning.assert_called_once_with("careful")
        _mock_storage.append_to_field.assert_called_once_with(123, "warnings", "careful")

    @patch("utils.Errors.Storage", _mock_storage)
    @patch("utils.Errors.Logger", _mock_logger)
    def test_record_warning_no_storage(self) -> None:
        """record_warning(update_storage=False) only logs."""
        _mock_logger.reset_mock()
        _mock_storage.reset_mock()
        record_warning(123, "nope", update_storage=False)

        _mock_logger.warning.assert_called_once_with("nope")
        _mock_storage.append_to_field.assert_not_called()
