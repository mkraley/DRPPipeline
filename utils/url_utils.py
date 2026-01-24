"""
Utilities for URL validation and access.

Provides functions for validating URLs and checking their availability.
"""

from typing import Tuple
import requests


def is_valid_url(url: str) -> bool:
    """
    Validate that URL is a valid HTTP/HTTPS URL.
    
    Args:
        url: URL to validate
        
    Returns:
        True if URL is valid, False otherwise
        
    Example:
        >>> is_valid_url("https://example.com")
        True
        >>> is_valid_url("not-a-url")
        False
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    return url.startswith('http://') or url.startswith('https://')


def access_url(url: str, timeout: int = 30) -> Tuple[bool, str]:
    """
    Access a URL and return status information.
    
    Args:
        url: URL to access
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (success: bool, status_message: str)
        
    Example:
        >>> success, status = access_url("https://example.com")
        >>> success
        True
        >>> status
        'Success'
    """
    try:
        response = requests.get(url, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            return True, "Success"
        else:
            return False, f"HTTP {response.status_code}"
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except requests.exceptions.ConnectionError:
        return False, "Connection Error"
    except requests.exceptions.TooManyRedirects:
        return False, "Too Many Redirects"
    except requests.exceptions.RequestException as e:
        return False, f"Error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected Error: {str(e)}"
