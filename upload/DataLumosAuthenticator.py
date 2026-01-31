"""
DataLumos authentication handler.

Handles login flow using Playwright including email/password authentication
and "Verifying you are human" checks.
"""

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.Logger import Logger


class DataLumosAuthenticator:
    """
    Handles authentication to DataLumos.
    
    Supports email/password authentication and handles
    various verification challenges that may appear.
    
    Usage:
        authenticator = DataLumosAuthenticator(page)
        authenticator.authenticate(username, password)
    """
    
    HOME_URL = "https://www.icpsr.umich.edu/sites/datalumos/home"
    
    def __init__(self, page: Page, timeout: int = 30000) -> None:
        """
        Initialize the authenticator.
        
        Args:
            page: Playwright Page object
            timeout: Default timeout in milliseconds
        """
        self._page = page
        self._timeout = timeout
    
    def authenticate(self, username: str, password: str) -> bool:
        """
        Authenticate to DataLumos with email and password.
        
        Navigates to the home page, clicks login, fills credentials,
        and submits the form.
        
        Args:
            username: Email address for login
            password: Password for login
            
        Returns:
            True if authentication succeeded
            
        Raises:
            RuntimeError: If authentication fails
        """
        Logger.info("Starting DataLumos authentication")
        
        # Navigate to home page
        Logger.debug(f"Navigating to {self.HOME_URL}")
        self._page.goto(self.HOME_URL, wait_until="domcontentloaded")
        self.wait_for_verification()
        
        # Click Login button
        Logger.debug("Looking for Login button")
        login_button = self._find_login_button()
        if login_button is None:
            raise RuntimeError("Could not find Login button on DataLumos home page")
        
        login_button.click()
        self.wait_for_verification()
        
        # Click "Sign in with Email" button
        Logger.debug("Looking for 'Sign in with Email' button")
        try:
            email_login_button = self._page.locator("#kc-emaillogin")
            email_login_button.click()
        except PlaywrightTimeoutError:
            raise RuntimeError("Could not find 'Sign in with Email' button")
        
        self.wait_for_verification()
        
        # Fill in username
        Logger.debug("Filling in username")
        try:
            username_input = self._page.locator("input#username, input[name='username']").first
            username_input.fill(username)
        except PlaywrightTimeoutError:
            raise RuntimeError("Could not find username input field")
        
        # Fill in password
        Logger.debug("Filling in password")
        try:
            password_input = self._page.locator("input#password, input[name='password']").first
            password_input.fill(password)
        except PlaywrightTimeoutError:
            raise RuntimeError("Could not find password input field")
        
        # Click Sign In button
        Logger.debug("Clicking Sign In button")
        try:
            submit_button = self._page.locator(
                "input[type='submit'][value='Sign In'], "
                "input.pf-c-button.btn.btn-primary[type='submit'], "
                "button[type='submit']"
            ).first
            submit_button.click()
        except PlaywrightTimeoutError:
            # Fallback: press Enter on password field
            Logger.debug("Sign In button not found, pressing Enter")
            password_input.press("Enter")
        
        # Wait for sign-in to complete
        Logger.debug("Waiting for sign-in to complete")
        self._page.wait_for_timeout(3000)  # Brief wait for redirect
        
        # Verify authentication succeeded
        if not self.is_authenticated():
            # Check for error messages on the page
            error_message = self._get_login_error()
            if error_message:
                raise RuntimeError(f"Authentication failed: {error_message}")
            raise RuntimeError("Authentication failed: unknown error")
        
        Logger.info("DataLumos authentication successful")
        return True
    
    def _find_login_button(self) -> object:
        """
        Find the Login button on the home page.
        
        Returns:
            Locator for the login button, or None if not found
        """
        # Try to find button or link with "Login" text
        selectors = [
            "button:has-text('Login')",
            "a:has-text('Login')",
            "[role='button']:has-text('Login')",
        ]
        
        for selector in selectors:
            try:
                locator = self._page.locator(selector).first
                if locator.is_visible(timeout=2000):
                    return locator
            except PlaywrightTimeoutError:
                continue
        
        return None
    
    def _get_login_error(self) -> str:
        """
        Get any error message displayed on the login page.
        
        Returns:
            Error message text, or empty string if no error found
        """
        error_selectors = [
            ".alert-error",
            ".error-message",
            "#error",
            "[role='alert']",
        ]
        
        for selector in error_selectors:
            try:
                error_elem = self._page.locator(selector).first
                if error_elem.is_visible(timeout=1000):
                    return error_elem.inner_text()
            except PlaywrightTimeoutError:
                continue
        
        return ""
    
    def wait_for_verification(self, timeout: int = 30000) -> bool:
        """
        Wait for "Verifying you are human" message to complete.
        
        Checks for various forms of verification messages and waits
        for them to disappear.
        
        Args:
            timeout: Maximum time to wait in milliseconds
            
        Returns:
            True if verification completed or wasn't needed
        """
        verification_selectors = [
            "//*[contains(text(), 'Verifying you are human')]",
            "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'verifying')]",
            "[class*='verifying']",
            "[id*='verifying']",
        ]
        
        for selector in verification_selectors:
            try:
                # Check if verification element exists
                if selector.startswith("//"):
                    locator = self._page.locator(f"xpath={selector}")
                else:
                    locator = self._page.locator(selector)
                
                # If element is visible, wait for it to disappear
                if locator.count() > 0 and locator.first.is_visible(timeout=1000):
                    Logger.debug("Human verification detected, waiting for completion")
                    locator.first.wait_for(state="hidden", timeout=timeout)
                    Logger.debug("Verification completed")
                    break
            except PlaywrightTimeoutError:
                continue
        
        # Brief additional wait for page stability
        self._page.wait_for_timeout(500)
        return True
    
    def is_authenticated(self) -> bool:
        """
        Check if the current session is authenticated.
        
        Looks for indicators that the user is logged in, such as:
        - Presence of workspace link
        - Absence of login button
        - User menu or profile elements
        
        Returns:
            True if user appears to be logged in
        """
        # Check if we're on a page that requires authentication
        current_url = self._page.url.lower()
        
        # If we're still on the login page, not authenticated
        if "login" in current_url or "signin" in current_url:
            return False
        
        # Check for elements that indicate logged-in state
        authenticated_indicators = [
            # Workspace link suggests user is logged in
            "a[href*='workspace']",
            # User menu or profile
            "[class*='user-menu']",
            "[class*='profile']",
            # Logout link
            "a:has-text('Logout')",
            "a:has-text('Sign out')",
        ]
        
        for selector in authenticated_indicators:
            try:
                locator = self._page.locator(selector).first
                if locator.is_visible(timeout=2000):
                    return True
            except PlaywrightTimeoutError:
                continue
        
        # If redirected away from login page, likely authenticated
        if "datalumos" in current_url and "login" not in current_url:
            return True
        
        return False
