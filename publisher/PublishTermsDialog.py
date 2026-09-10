"""
Complete the DataLumos Terms and Conditions modal during publish.

After ``Proceed to Publish``, openICPSR shows ``#reviewTermsDialogId``. Two
variants appear:

- **Full form**: disclosure radios, optional distribution (defaults to
  restricted when shown), delayed dissemination, license, deposit agreement.
- **Short form**: permanence notice and ``Publish Data`` only (no disclosure
  controls). Seen on some projects; click through and surface DataLumos
  validation errors such as ``Please complete all required fields``.

Government BTS deposits use public download when offered and Public Domain Mark.
"""

from __future__ import annotations

import time

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.Args import Args
from utils.Logger import Logger

TERMS_DIALOG_SELECTOR = "#reviewTermsDialogId"
PUBLIC_DOMAIN_LICENSE_VALUE = "15"
REQUIRED_FIELDS_MESSAGE = "Please complete all required fields"

# Required disclosure answers (distribution may disappear after these).
_REQUIRED_DISCLOSURE_IDS = ("noDisclosure", "sensitiveNo")
# Shown when DataLumos keeps the distribution section; prefer public download.
_OPTIONAL_PUBLIC_OPTION_ID = "publicOption"
_REQUIRED_AFTER_DISCLOSURE_IDS = ("noDelay",)


class PublishTermsDialog:
    """
    Fill and confirm the DataLumos publish Terms and Conditions dialog.

    Prefer ``label[for=...]`` clicks because styled radios are often not
    actionability-visible to Playwright even when present in the DOM.
    """

    def complete(self, page: Page) -> None:
        """
        Wait for the terms modal and answer controls when the full form is shown.

        Args:
            page: Playwright page after clicking Proceed to Publish.

        Raises:
            PlaywrightTimeoutError: If the dialog never becomes ready.
            RuntimeError: If a required full-form control is missing.
        """
        self._wait_for_dialog(page)
        variant = self._detect_dialog_variant(page)
        if variant == "short":
            Logger.info(
                "Terms dialog is the short variant (no disclosure form); "
                "Publish Data will be clicked next"
            )
            return
        Logger.info("Terms dialog is the full disclosure form; filling answers")
        for element_id in _REQUIRED_DISCLOSURE_IDS:
            self._click_labeled_control(page, element_id, required=True)
        page.wait_for_timeout(500)
        self._click_labeled_control(
            page, _OPTIONAL_PUBLIC_OPTION_ID, required=False
        )
        for element_id in _REQUIRED_AFTER_DISCLOSURE_IDS:
            self._click_labeled_control(page, element_id, required=True)
        self._select_public_domain_license(page)
        self._click_labeled_control(page, "depositAgree", required=True)

    def _wait_for_dialog(self, page: Page) -> None:
        """
        Wait until the Terms and Conditions modal is visible.

        Args:
            page: Playwright page after Proceed to Publish.
        """
        timeout_ms = int(Args.upload_timeout)
        dialog = page.locator(TERMS_DIALOG_SELECTOR)
        try:
            dialog.wait_for(state="visible", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            Logger.error(
                "Terms dialog %s did not become visible within %sms",
                TERMS_DIALOG_SELECTOR,
                timeout_ms,
            )
            raise
        Logger.info("Terms and Conditions dialog is visible")
        page.wait_for_timeout(500)

    def _detect_dialog_variant(self, page: Page) -> str:
        """
        Return ``full`` or ``short`` once the dialog content has settled.

        ``Publish Data`` often appears immediately in a disabled state while the
        disclosure form is still loading. Treat the dialog as short only when
        that button is enabled and disclosure controls never appear.

        Args:
            page: Playwright page with the terms dialog visible.

        Returns:
            ``\"full\"`` or ``\"short\"``.

        Raises:
            RuntimeError: If Publish Data stays disabled (likely incomplete
                review metadata) or the dialog never becomes ready.
        """
        timeout_ms = int(Args.upload_timeout)
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        dialog = page.locator(TERMS_DIALOG_SELECTOR)
        enabled_publish_seen_at: float | None = None
        saw_disabled_publish = False

        while time.monotonic() < deadline:
            if page.locator("#noDisclosure").count() > 0:
                page.wait_for_timeout(300)
                return "full"

            publish_data = dialog.locator(
                "button.btn-primary:has-text('Publish Data')"
            )
            if publish_data.count() == 0:
                page.wait_for_timeout(250)
                continue

            if publish_data.first.is_disabled():
                saw_disabled_publish = True
                enabled_publish_seen_at = None
                page.wait_for_timeout(250)
                continue

            # Enabled Publish Data without disclosure yet — wait briefly for a
            # late full-form render before accepting the short variant.
            now = time.monotonic()
            if enabled_publish_seen_at is None:
                enabled_publish_seen_at = now
                page.wait_for_timeout(2000)
                continue
            if now - enabled_publish_seen_at < 2.0:
                page.wait_for_timeout(250)
                continue
            return "short"

        if saw_disabled_publish:
            raise RuntimeError(
                "Publish Data stayed disabled and the disclosure form never "
                "appeared. DataLumos usually does this when review metadata is "
                "incomplete or still loading — wait on the review page, confirm "
                "required fields are saved, then retry."
            )
        Logger.error(
            "Terms dialog never showed disclosure controls or Publish Data "
            "within %sms",
            timeout_ms,
        )
        raise PlaywrightTimeoutError(
            "Terms dialog content did not become ready"
        )

    def _click_labeled_control(
        self,
        page: Page,
        element_id: str,
        *,
        required: bool,
    ) -> None:
        """
        Click the label associated with a radio or checkbox by element id.

        Falls back to a forced check on the input when no label is present.

        Args:
            page: Playwright page with the terms dialog open.
            element_id: DOM id of the input (without ``#``).
            required: When False, skip quietly if the control is absent.
        """
        label = page.locator(f"label[for='{element_id}']")
        if label.count() > 0:
            Logger.debug("Clicking terms label for #%s", element_id)
            label.first.click(timeout=int(Args.upload_timeout))
            page.wait_for_timeout(300)
            return

        control = page.locator(f"#{element_id}")
        if control.count() == 0:
            if required:
                raise RuntimeError(
                    f"Terms dialog control #{element_id} not found"
                )
            Logger.info(
                "Terms dialog optional control #%s not present; skipping",
                element_id,
            )
            return

        Logger.debug("Force-checking terms control #%s", element_id)
        control.first.check(force=True, timeout=int(Args.upload_timeout))
        page.wait_for_timeout(300)

    def _select_public_domain_license(self, page: Page) -> None:
        """
        Select Public Domain Mark in the license dropdown.

        Args:
            page: Playwright page with the terms dialog open.
        """
        license_select = page.locator("#select-license")
        try:
            license_select.wait_for(
                state="attached", timeout=int(Args.upload_timeout)
            )
        except PlaywrightTimeoutError:
            raise RuntimeError("Terms dialog #select-license not found") from None
        Logger.info(
            "Selecting Public Domain Mark license (value=%s)",
            PUBLIC_DOMAIN_LICENSE_VALUE,
        )
        license_select.select_option(PUBLIC_DOMAIN_LICENSE_VALUE)
        page.wait_for_timeout(300)

    def click_publish_data(self, page: Page) -> None:
        """
        Click ``Publish Data`` in the terms dialog, failing fast if disabled.

        Args:
            page: Playwright page with the terms dialog open.

        Raises:
            RuntimeError: If the button is disabled or required-fields validation
                is shown.
        """
        dialog_publish = page.locator(
            f"{TERMS_DIALOG_SELECTOR} button.btn-primary:has-text('Publish Data')"
        )
        if dialog_publish.count() > 0:
            publish_btn = dialog_publish.first
        else:
            publish_btn = page.locator(
                "button.btn-primary:has-text('Publish Data')"
            ).first

        publish_btn.wait_for(state="visible", timeout=int(Args.upload_timeout))
        if publish_btn.is_disabled():
            self.assert_no_required_fields_error(page)
            raise RuntimeError(
                "Publish Data is disabled; complete required metadata on the "
                "review page (e.g. Government Agency/Principal Investigator), "
                "then retry"
            )

        Logger.info("Clicking Publish Data")
        publish_btn.scroll_into_view_if_needed()
        publish_btn.click(timeout=15000)
        page.wait_for_timeout(2000)
        self.assert_no_required_fields_error(page)

    def assert_no_required_fields_error(self, page: Page) -> None:
        """
        Raise if DataLumos shows the required-fields validation message.

        Args:
            page: Playwright page after clicking Publish Data.

        Raises:
            RuntimeError: When the required-fields banner is visible.
        """
        banner = page.get_by_text(REQUIRED_FIELDS_MESSAGE, exact=False)
        try:
            if banner.count() > 0 and banner.first.is_visible(timeout=2000):
                raise RuntimeError(
                    "DataLumos rejected publish: "
                    f"{REQUIRED_FIELDS_MESSAGE} "
                    "(complete required metadata on the review page, then retry)"
                )
        except PlaywrightTimeoutError:
            return
