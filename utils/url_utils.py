"""
Utilities for URL validation and access.

Provides functions for validating URLs and checking their availability.
"""

from typing import Dict, Tuple, Optional
import requests

# Headers to mimic a real browser and avoid abuse/filter blocks.
BROWSER_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


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
        response = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers=BROWSER_HEADERS,
        )
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


def infer_file_type(url: str, content_type: Optional[str] = None) -> str:
    """
    Infer file type/extension from URL path or Content-Type header.

    Prefers URL path extension when present; otherwise maps common Content-Type
    values to extensions (e.g. text/csv -> csv, application/json -> json).

    Args:
        url: Resource URL (may have path with extension)
        content_type: Optional Content-Type header value (e.g. "text/csv")

    Returns:
        Lowercase file type string (e.g. "csv", "json", "html") or "unknown".
    """
    from urllib.parse import urlparse, unquote

    parsed = urlparse(unquote(url))
    path = parsed.path.rstrip("/")
    if "." in path.split("/")[-1]:
        ext = path.split(".")[-1].lower()
        if ext and len(ext) <= 5 and ext.isalnum():
            return ext

    if content_type:
        ct = content_type.lower().strip()
        mapping = {
            "text/csv": "csv",
            "application/json": "json",
            "application/xml": "xml",
            "text/xml": "xml",
            "text/html": "html",
            "application/rdf+xml": "rdf",
            "application/zip": "zip",
            "application/x-zip-compressed": "zip",
            "application/vnd.ms-excel": "xls",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
            "text/plain": "txt",
        }
        return mapping.get(ct, ct.split("/")[-1] if "/" in ct else "unknown")
    return "unknown"


# Phrases in HTML body that indicate a "page not found" error page (case-insensitive).
_HTML_NOT_FOUND_PHRASES = (
    "page not found",
    "the page you requested could not be found",
    "sorry, the page you requested could not be found",
)


def _html_body_looks_like_not_found(body: str) -> bool:
    """Return True if HTML body contains not-found error phrases."""
    lower = body.lower()
    return any(phrase in lower for phrase in _HTML_NOT_FOUND_PHRASES)


def fetch_url_head(
    url: str, timeout: int = 30
) -> Tuple[int, Optional[str], Optional[str]]:
    """
    Perform a HEAD request and return status code, Content-Type, and error message.

    Treats as 404: HTTP 404, connection errors ("Failed to establish a new connection"),
    and 200 responses with HTML body containing "page not found" or similar phrases.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Tuple of (status_code: int, content_type: Optional[str], error_message: Optional[str]).
        On success: (status_code, content_type, None).
        On HTTP 404 or not-found-like: (404, None, None) or (404, None, error_msg).
        On other exception: (-1, None, str(cause)).
    """
    try:
        response = requests.head(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers=BROWSER_HEADERS,
        )
        content_type = response.headers.get("Content-Type")
        if content_type and ";" in content_type:
            content_type = content_type.split(";")[0].strip()

        # If 200 with HTML, fetch body and check for "page not found" style content
        if response.status_code == 200 and content_type and "text/html" in content_type.lower():
            get_resp = requests.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
                headers=BROWSER_HEADERS,
            )
            get_resp.raw.decode_content = True
            chunk = get_resp.raw.read(16384)
            try:
                text = chunk.decode("utf-8", errors="ignore")
            except Exception:
                text = chunk.decode("latin-1", errors="ignore")
            if _html_body_looks_like_not_found(text):
                return 404, None, None

        return response.status_code, content_type, None
    except Exception as exc:
        cause = exc.__cause__ if exc.__cause__ is not None else exc
        err_str = str(cause)
        if "Failed to establish a new connection" in err_str:
            return 404, None, err_str
        return -1, None, err_str
