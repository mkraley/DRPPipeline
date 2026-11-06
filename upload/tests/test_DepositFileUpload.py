"""Unit tests for posting files through the deposit upload endpoints."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.Logger import Logger

from upload.DepositFileUpload import (
    DepositFileUpload,
    interpret_upload_response,
    upload_url,
)


class TestUploadResponse(unittest.TestCase):
    """The modal treats some 200 bodies as success and others as rejection."""

    def test_queued_body_is_accepted(self) -> None:
        """A file object with no failure status is the queue message."""
        interpret_upload_response(200, '{"name": "notes.txt"}', "uploadRawFile")

    def test_zip_body_is_accepted(self) -> None:
        """Import From Zip succeeds when the body type is zip."""
        interpret_upload_response(200, '{"type": "zip", "name": "bundle.zip"}', "uploadZipFile")

    def test_empty_body_means_the_file_is_already_there(self) -> None:
        """The modal shows its duplicate-file error when the body is empty."""
        with self.assertRaises(RuntimeError) as caught:
            interpret_upload_response(200, "", "uploadRawFile")
        self.assertIn("already", str(caught.exception))

    def test_failed_file_status_is_rejected(self) -> None:
        """A failed file status surfaces the server description."""
        with self.assertRaises(RuntimeError) as caught:
            interpret_upload_response(
                200,
                '{"fileStatus": "failed", "description": "too large"}',
                "uploadRawFile",
            )
        self.assertIn("too large", str(caught.exception))

    def test_rejected_status_is_reported(self) -> None:
        """A non-200 response names the endpoint and status."""
        with self.assertRaises(RuntimeError) as caught:
            interpret_upload_response(401, "denied", "uploadRawFile")
        self.assertIn("failed (401)", str(caught.exception))


class TestDepositFileUpload(unittest.TestCase):
    """File posts use the bearer token and do not open the project page."""

    def setUp(self) -> None:
        """Logger is required when an upload is announced."""
        Logger.initialize(log_level="ERROR", log_file=False)
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        """Remove the temporary project folder."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_url_matches_the_upload_button(self) -> None:
        """The query carries the project path, modified time, and MIME type."""
        path = self.temp_dir / "notes.txt"
        path.write_text("hi", encoding="utf-8")
        url = upload_url("42", path, zip_upload=False)
        self.assertIn("/deposit/uploadRawFile?", url)
        self.assertIn("resourceId=/datalumos/42", url)
        self.assertIn(f"lastModified={int(path.stat().st_mtime * 1000)}", url)
        self.assertIn("type=text/plain", url)

    def test_file_post_uses_the_upload_field_and_skips_the_page(self) -> None:
        """One file is streamed as multipart field file."""
        path = self.temp_dir / "notes.txt"
        path.write_text("hi", encoding="utf-8")
        page = MagicMock()
        page.context.cookies.return_value = [
            {"name": "JSESSIONID", "value": "abc", "domain": ".icpsr.umich.edu", "path": "/"}
        ]
        response = MagicMock(status_code=200, text='{"name": "notes.txt"}')
        with patch("upload.DepositFileUpload.requests.post", return_value=response) as post:
            DepositFileUpload(page, "jwt-saved").upload_folder("42", str(self.temp_dir))
        page.goto.assert_not_called()
        self.assertIn("/uploadRawFile?resourceId=/datalumos/42", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer jwt-saved")
        self.assertEqual(post.call_args.kwargs["files"]["file"][0], "notes.txt")

    def test_subfolder_uses_the_zip_endpoint(self) -> None:
        """A folder with a subfolder is one uploadZipFile post."""
        (self.temp_dir / "inner").mkdir()
        (self.temp_dir / "inner" / "notes.txt").write_text("hi", encoding="utf-8")
        page = MagicMock()
        page.context.cookies.return_value = []
        response = MagicMock(status_code=200, text='{"type": "zip"}')
        with patch("upload.DepositFileUpload.requests.post", return_value=response) as post:
            DepositFileUpload(page, "jwt-saved").upload_folder("42", str(self.temp_dir))
        self.assertIn("/uploadZipFile?resourceId=/datalumos/42", post.call_args.args[0])
        self.assertTrue(str(post.call_args.kwargs["files"]["file"][0]).endswith(".zip"))

    def test_rejected_token_is_forgotten(self) -> None:
        """A 401 drops the token so the next project can read a new one."""
        (self.temp_dir / "notes.txt").write_text("hi", encoding="utf-8")
        page = MagicMock()
        page.context.cookies.return_value = []
        response = MagicMock(status_code=401, text="denied")
        client = DepositFileUpload(page, "jwt-saved")
        with patch("upload.DepositFileUpload.requests.post", return_value=response):
            with self.assertRaises(RuntimeError):
                client.upload_folder("42", str(self.temp_dir))
        self.assertEqual(client.token, "")

    def test_worker_threads_do_not_touch_the_browser(self) -> None:
        """Cookies are read on the caller thread. Workers only receive a copy."""
        (self.temp_dir / "a.txt").write_text("a", encoding="utf-8")
        (self.temp_dir / "b.txt").write_text("b", encoding="utf-8")
        page = MagicMock()
        caller = threading.get_ident()
        cookie_threads: list[int] = []
        post_threads: list[int] = []

        def cookies() -> list[dict[str, str]]:
            cookie_threads.append(threading.get_ident())
            return [{"name": "JSESSIONID", "value": "abc", "domain": ".icpsr.umich.edu", "path": "/"}]

        def post(*_args: object, **_kwargs: object) -> MagicMock:
            post_threads.append(threading.get_ident())
            return MagicMock(status_code=200, text='{"name": "a.txt"}')

        page.context.cookies.side_effect = cookies
        with patch("upload.DepositFileUpload.requests.post", side_effect=post):
            DepositFileUpload(page, "jwt-saved").upload_folder("42", str(self.temp_dir))
        self.assertTrue(cookie_threads)
        self.assertTrue(all(thread_id == caller for thread_id in cookie_threads))
        self.assertTrue(post_threads)
        self.assertTrue(all(thread_id != caller for thread_id in post_threads))


if __name__ == "__main__":
    unittest.main()
