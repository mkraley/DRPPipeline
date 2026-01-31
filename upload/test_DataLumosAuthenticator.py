"""
Unit tests for DataLumosAuthenticator.
"""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.Logger import Logger
from upload.DataLumosAuthenticator import DataLumosAuthenticator


class TestDataLumosAuthenticator(unittest.TestCase):
    """Test cases for DataLumosAuthenticator."""

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize Logger once for all tests."""
        Logger.initialize(log_level="WARNING")

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self.mock_page = MagicMock()
        self.authenticator = DataLumosAuthenticator(self.mock_page, timeout=5000)

    def test_init(self) -> None:
        """Test authenticator initialization."""
        self.assertEqual(self.authenticator._page, self.mock_page)
        self.assertEqual(self.authenticator._timeout, 5000)

    def test_home_url_constant(self) -> None:
        """Test HOME_URL is correctly defined."""
        self.assertEqual(
            DataLumosAuthenticator.HOME_URL,
            "https://www.icpsr.umich.edu/sites/datalumos/home"
        )

    def test_wait_for_verification_no_verification_present(self) -> None:
        """Test wait_for_verification returns True when no verification needed."""
        # Mock locator that returns count of 0 (no verification elements)
        mock_locator = MagicMock()
        mock_locator.count.return_value = 0
        self.mock_page.locator.return_value = mock_locator
        
        result = self.authenticator.wait_for_verification()
        self.assertTrue(result)

    def test_wait_for_verification_verification_present_and_completes(self) -> None:
        """Test wait_for_verification waits for verification to complete."""
        # Mock locator that finds a verification element
        mock_locator = MagicMock()
        mock_locator.count.return_value = 1
        mock_first = MagicMock()
        mock_first.is_visible.return_value = True
        mock_locator.first = mock_first
        self.mock_page.locator.return_value = mock_locator
        
        result = self.authenticator.wait_for_verification()
        
        self.assertTrue(result)
        # Should have waited for element to become hidden
        mock_first.wait_for.assert_called_once_with(state="hidden", timeout=60000)

    def test_is_authenticated_login_page(self) -> None:
        """Test is_authenticated returns False when on login page."""
        # Mock being on the login page
        type(self.mock_page).url = PropertyMock(return_value="https://example.com/login")
        
        result = self.authenticator.is_authenticated()
        self.assertFalse(result)

    def test_is_authenticated_signin_page(self) -> None:
        """Test is_authenticated returns False when on signin page."""
        type(self.mock_page).url = PropertyMock(return_value="https://example.com/signin")
        
        result = self.authenticator.is_authenticated()
        self.assertFalse(result)

    def test_is_authenticated_datalumos_page(self) -> None:
        """Test is_authenticated returns True when on DataLumos page."""
        type(self.mock_page).url = PropertyMock(
            return_value="https://www.datalumos.org/datalumos/workspace"
        )
        
        # Mock locator that doesn't find indicators (but URL is good)
        mock_locator = MagicMock()
        mock_locator.first.is_visible.side_effect = PlaywrightTimeoutError("timeout")
        self.mock_page.locator.return_value = mock_locator
        
        result = self.authenticator.is_authenticated()
        self.assertTrue(result)

    def test_is_authenticated_with_logout_link(self) -> None:
        """Test is_authenticated returns True when logout link visible."""
        type(self.mock_page).url = PropertyMock(
            return_value="https://example.com/dashboard"
        )
        
        # Mock finding a logout link
        mock_locator = MagicMock()
        mock_first = MagicMock()
        mock_first.is_visible.return_value = True
        mock_locator.first = mock_first
        self.mock_page.locator.return_value = mock_locator
        
        result = self.authenticator.is_authenticated()
        self.assertTrue(result)

    def test_find_login_button_found(self) -> None:
        """Test _find_login_button returns locator when button found."""
        mock_locator = MagicMock()
        mock_locator.first.is_visible.return_value = True
        self.mock_page.locator.return_value = mock_locator
        
        result = self.authenticator._find_login_button()
        self.assertIsNotNone(result)

    def test_find_login_button_not_found(self) -> None:
        """Test _find_login_button returns None when button not found."""
        mock_locator = MagicMock()
        mock_locator.first.is_visible.side_effect = PlaywrightTimeoutError("timeout")
        self.mock_page.locator.return_value = mock_locator
        
        result = self.authenticator._find_login_button()
        self.assertIsNone(result)

    def test_get_login_error_no_error(self) -> None:
        """Test _get_login_error returns empty string when no error."""
        mock_locator = MagicMock()
        mock_locator.first.is_visible.side_effect = PlaywrightTimeoutError("timeout")
        self.mock_page.locator.return_value = mock_locator
        
        result = self.authenticator._get_login_error()
        self.assertEqual(result, "")

    def test_get_login_error_with_error(self) -> None:
        """Test _get_login_error returns error message when present."""
        mock_locator = MagicMock()
        mock_first = MagicMock()
        mock_first.is_visible.return_value = True
        mock_first.inner_text.return_value = "Invalid credentials"
        mock_locator.first = mock_first
        self.mock_page.locator.return_value = mock_locator
        
        result = self.authenticator._get_login_error()
        self.assertEqual(result, "Invalid credentials")


class TestDataLumosAuthenticatorAuthenticate(unittest.TestCase):
    """Test cases for the authenticate method."""

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize Logger once for all tests."""
        Logger.initialize(log_level="WARNING")

    def setUp(self) -> None:
        """Set up test environment."""
        self.mock_page = MagicMock()
        self.authenticator = DataLumosAuthenticator(self.mock_page, timeout=5000)

    def test_authenticate_no_login_button_raises(self) -> None:
        """Test authenticate raises when login button not found."""
        # Mock _find_login_button to return None
        with patch.object(self.authenticator, '_find_login_button', return_value=None):
            with patch.object(self.authenticator, 'wait_for_verification'):
                with self.assertRaises(RuntimeError) as context:
                    self.authenticator.authenticate("user@test.com", "password")
                
                self.assertIn("Login button", str(context.exception))

    def test_authenticate_email_button_not_found_raises(self) -> None:
        """Test authenticate raises when email login button not found."""
        mock_login_button = MagicMock()
        
        # Mock email login button - click() times out when element not found
        mock_email_locator = MagicMock()
        mock_email_locator.click.side_effect = PlaywrightTimeoutError("timeout")
        self.mock_page.locator.return_value = mock_email_locator
        
        with patch.object(self.authenticator, '_find_login_button', return_value=mock_login_button):
            with patch.object(self.authenticator, 'wait_for_verification'):
                with self.assertRaises(RuntimeError) as context:
                    self.authenticator.authenticate("user@test.com", "password")
                
                self.assertIn("Sign in with Email", str(context.exception))

    def test_authenticate_success_flow(self) -> None:
        """Test successful authentication flow."""
        mock_login_button = MagicMock()
        mock_email_button = MagicMock()
        mock_username_input = MagicMock()
        mock_password_input = MagicMock()
        mock_submit_button = MagicMock()
        
        # Set up locator to return different mocks based on selector
        def locator_side_effect(selector):
            if "kc-emaillogin" in selector:
                return mock_email_button
            elif "username" in selector:
                mock = MagicMock()
                mock.first = mock_username_input
                return mock
            elif "password" in selector:
                mock = MagicMock()
                mock.first = mock_password_input
                return mock
            elif "submit" in selector:
                mock = MagicMock()
                mock.first = mock_submit_button
                return mock
            return MagicMock()
        
        self.mock_page.locator.side_effect = locator_side_effect
        
        with patch.object(self.authenticator, '_find_login_button', return_value=mock_login_button):
            with patch.object(self.authenticator, 'wait_for_verification'):
                with patch.object(self.authenticator, 'is_authenticated', return_value=True):
                    result = self.authenticator.authenticate("user@test.com", "password")
        
        self.assertTrue(result)
        mock_login_button.click.assert_called_once()
        mock_email_button.click.assert_called_once()
        mock_username_input.fill.assert_called_once_with("user@test.com")
        mock_password_input.fill.assert_called_once_with("password")


if __name__ == "__main__":
    unittest.main()
