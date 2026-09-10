"""
Unit tests for PublishTermsDialog.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.Args import Args
from utils.Logger import Logger
from publisher.PublishTermsDialog import (
    PUBLIC_DOMAIN_LICENSE_VALUE,
    REQUIRED_FIELDS_MESSAGE,
    TERMS_DIALOG_SELECTOR,
    PublishTermsDialog,
)


class TestPublishTermsDialog(unittest.TestCase):
    """Tests for DataLumos terms modal completion."""

    def setUp(self) -> None:
        """Initialize Args and Logger for timeouts."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "publisher"]
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.dialog = PublishTermsDialog()

    def tearDown(self) -> None:
        """Restore argv and Args."""
        sys.argv = self._original_argv
        Args._initialized = False

    def test_complete_full_form_fills_controls(self) -> None:
        """Full disclosure form answers radios, license, and agree."""
        page = MagicMock()
        self.dialog._wait_for_dialog = MagicMock()  # type: ignore[method-assign]
        self.dialog._detect_dialog_variant = MagicMock(return_value="full")  # type: ignore[method-assign]
        self.dialog._click_labeled_control = MagicMock()  # type: ignore[method-assign]
        self.dialog._select_public_domain_license = MagicMock()  # type: ignore[method-assign]

        self.dialog.complete(page)

        clicked = [
            c.args[1] for c in self.dialog._click_labeled_control.call_args_list
        ]
        self.assertEqual(
            clicked,
            [
                "noDisclosure",
                "sensitiveNo",
                "publicOption",
                "noDelay",
                "depositAgree",
            ],
        )
        self.dialog._select_public_domain_license.assert_called_once_with(page)

    def test_complete_short_form_skips_disclosure(self) -> None:
        """Short dialog returns without clicking disclosure controls."""
        page = MagicMock()
        self.dialog._wait_for_dialog = MagicMock()  # type: ignore[method-assign]
        self.dialog._detect_dialog_variant = MagicMock(return_value="short")  # type: ignore[method-assign]
        self.dialog._click_labeled_control = MagicMock()  # type: ignore[method-assign]

        self.dialog.complete(page)

        self.dialog._click_labeled_control.assert_not_called()

    def test_detect_variant_full_when_no_disclosure_present(self) -> None:
        """Variant is full as soon as #noDisclosure exists."""
        page = MagicMock()
        no_disclosure = MagicMock()
        no_disclosure.count.return_value = 1
        page.locator.side_effect = lambda sel: (
            no_disclosure if sel == "#noDisclosure" else MagicMock()
        )
        self.assertEqual(self.dialog._detect_dialog_variant(page), "full")

    def test_detect_variant_short_when_only_publish_data(self) -> None:
        """Variant is short when Publish Data is enabled and no disclosure."""
        page = MagicMock()
        no_disclosure = MagicMock()
        no_disclosure.count.return_value = 0
        dialog = MagicMock()
        publish_btn = MagicMock()
        publish_btn.count.return_value = 1
        publish_btn.first.is_disabled.return_value = False
        dialog.locator.return_value = publish_btn
        page.locator.side_effect = lambda sel: (
            no_disclosure if sel == "#noDisclosure" else dialog
        )
        # deadline init, while#1, now#1 (arm), while#2, now#2 (accept after 2s).
        with patch.object(page, "wait_for_timeout"), patch(
            "publisher.PublishTermsDialog.time.monotonic",
            side_effect=[0.0, 0.1, 0.1, 0.2, 3.0],
        ):
            self.assertEqual(self.dialog._detect_dialog_variant(page), "short")

    def test_detect_variant_waits_while_publish_data_disabled(self) -> None:
        """Disabled Publish Data alone must not be treated as short form."""
        page = MagicMock()
        no_disclosure = MagicMock()
        no_disclosure.count.return_value = 0
        dialog = MagicMock()
        publish_btn = MagicMock()
        publish_btn.count.return_value = 1
        publish_btn.first.is_disabled.return_value = True
        dialog.locator.return_value = publish_btn
        page.locator.side_effect = lambda sel: (
            no_disclosure if sel == "#noDisclosure" else dialog
        )
        with patch.object(page, "wait_for_timeout"), patch(
            "publisher.PublishTermsDialog.time.monotonic",
            side_effect=[0.0, 0.1, 120.0],
        ), patch("publisher.PublishTermsDialog.Args") as mock_args:
            mock_args.upload_timeout = 1000
            with self.assertRaises(RuntimeError) as ctx:
                self.dialog._detect_dialog_variant(page)
        self.assertIn("Publish Data stayed disabled", str(ctx.exception))

    def test_click_publish_data_raises_when_disabled(self) -> None:
        """Disabled Publish Data fails fast with a metadata error."""
        page = MagicMock()
        btn = MagicMock()
        btn.count.return_value = 1
        btn.first = btn
        btn.is_disabled.return_value = True
        page.locator.return_value = btn
        self.dialog.assert_no_required_fields_error = MagicMock()  # type: ignore[method-assign]

        with self.assertRaises(RuntimeError) as ctx:
            self.dialog.click_publish_data(page)
        self.assertIn("Publish Data is disabled", str(ctx.exception))
        btn.click.assert_not_called()

    def test_click_publish_data_clicks_when_enabled(self) -> None:
        """Enabled Publish Data is scrolled into view and clicked."""
        page = MagicMock()
        btn = MagicMock()
        btn.count.return_value = 1
        btn.first = btn
        btn.is_disabled.return_value = False
        page.locator.return_value = btn
        self.dialog.assert_no_required_fields_error = MagicMock()  # type: ignore[method-assign]

        self.dialog.click_publish_data(page)

        btn.scroll_into_view_if_needed.assert_called_once()
        btn.click.assert_called_once()
        self.dialog.assert_no_required_fields_error.assert_called()

    def test_click_labeled_control_falls_back_to_force_check(self) -> None:
        """When no label exists, force-check the input."""
        page = MagicMock()
        label = MagicMock()
        label.count.return_value = 0
        control = MagicMock()
        control.count.return_value = 1
        page.locator.side_effect = [label, control]

        self.dialog._click_labeled_control(page, "noDisclosure", required=True)

        page.locator.assert_has_calls(
            [call("label[for='noDisclosure']"), call("#noDisclosure")]
        )
        control.first.check.assert_called_once_with(
            force=True, timeout=int(Args.upload_timeout)
        )

    def test_optional_control_missing_does_not_raise(self) -> None:
        """Optional controls absent from the DOM are skipped."""
        page = MagicMock()
        label = MagicMock()
        label.count.return_value = 0
        control = MagicMock()
        control.count.return_value = 0
        page.locator.side_effect = [label, control]

        self.dialog._click_labeled_control(page, "publicOption", required=False)

    def test_assert_no_required_fields_error_raises(self) -> None:
        """Visible required-fields banner becomes a RuntimeError."""
        page = MagicMock()
        banner = MagicMock()
        banner.count.return_value = 1
        banner.first.is_visible.return_value = True
        page.get_by_text.return_value = banner

        with self.assertRaises(RuntimeError) as ctx:
            self.dialog.assert_no_required_fields_error(page)
        self.assertIn(REQUIRED_FIELDS_MESSAGE, str(ctx.exception))

    def test_select_license_raises_when_missing(self) -> None:
        """Missing license dropdown raises a clear error."""
        page = MagicMock()
        select = MagicMock()
        select.wait_for.side_effect = PlaywrightTimeoutError("timeout")
        page.locator.return_value = select

        with self.assertRaises(RuntimeError) as ctx:
            self.dialog._select_public_domain_license(page)
        self.assertIn("#select-license", str(ctx.exception))

    def test_public_domain_license_value(self) -> None:
        """Public Domain Mark is option value 15 on DataLumos."""
        self.assertEqual(PUBLIC_DOMAIN_LICENSE_VALUE, "15")
        self.assertEqual(TERMS_DIALOG_SELECTOR, "#reviewTermsDialogId")


class TestPublisherRetryReset(unittest.TestCase):
    """Tests for workspace reset before publish retry."""

    def setUp(self) -> None:
        """Initialize Args, Logger, Storage, and publisher."""
        from storage import Storage
        from publisher.DataLumosPublisher import DataLumosPublisher

        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "publisher"]
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize(
            "StorageSQLLite", db_path=self.temp_dir / "test.db"
        )
        self.publisher = DataLumosPublisher()

    def tearDown(self) -> None:
        """Restore argv and reset Storage."""
        import shutil

        from storage import Storage

        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        Args._initialized = False
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_reset_navigates_to_project_url(self) -> None:
        """Retry reset returns to the workspace project URL."""
        page = MagicMock()
        self.publisher._wait_for_busy = MagicMock()  # type: ignore[method-assign]
        self.publisher._reset_to_project_workspace(page, "252928")
        page.goto.assert_called_once()
        url = page.goto.call_args.args[0]
        self.assertIn("252928", url)
        self.assertIn("goToLevel=project", url)

    def test_publish_workspace_resets_before_retry(self) -> None:
        """Failed first attempt triggers workspace reset then second try."""
        from storage import Storage

        drpid = Storage.create_record("https://example.com")
        Storage.update_record(
            drpid, {"status": "uploaded", "datalumos_id": "252928"}
        )
        page = MagicMock()
        self.publisher._reset_to_project_workspace = MagicMock()  # type: ignore[method-assign]
        self.publisher._run_publish_flow_once = MagicMock(  # type: ignore[method-assign]
            side_effect=[RuntimeError("boom"), (True, None)]
        )

        ok, err = self.publisher._publish_workspace(page, drpid)

        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(self.publisher._run_publish_flow_once.call_count, 2)
        self.publisher._reset_to_project_workspace.assert_called_once_with(
            page, "252928"
        )


if __name__ == "__main__":
    unittest.main()
