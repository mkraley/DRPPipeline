"""
Unit tests for DataLumosUploader (upload module).
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage import Storage
from utils.Args import Args
from utils.Errors import ProjectAbort
from utils.Logger import Logger

from upload.DataLumosUploader import (
    DataLumosUploader,
    _agency_values_for_upload,
    _warn_if_num_files_mismatch,
)
from upload.UploadIssueReporter import UploadIssueReporter


class TestDataLumosUploader(unittest.TestCase):
    """Test cases for DataLumosUploader module."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "upload"]

        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")

        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.temp_dir / "test_drp_pipeline.db"
        self.storage = Storage.initialize("StorageSQLLite", db_path=self.test_db_path)
        self.uploader = DataLumosUploader()

    def tearDown(self) -> None:
        """Clean up after each test."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_validate_project_missing_title(self) -> None:
        """Test validation fails when title is missing."""
        project = {"summary": "Test summary"}
        errors = self.uploader._validate_project(project)
        self.assertIn("Missing required field: title", errors)

    def test_validate_project_missing_summary(self) -> None:
        """Test validation fails when summary is missing."""
        project = {"title": "Test title"}
        errors = self.uploader._validate_project(project)
        self.assertIn("Missing required field: summary", errors)

    def test_validate_project_valid(self) -> None:
        """Test validation passes with required fields."""
        project = {"title": "Test title", "summary": "Test summary"}
        errors = self.uploader._validate_project(project)
        self.assertEqual(errors, [])

    def test_validate_project_folder_not_exists(self) -> None:
        """Test validation fails when folder_path doesn't exist."""
        project = {
            "title": "Test title",
            "summary": "Test summary",
            "folder_path": "/nonexistent/path/to/folder",
        }
        errors = self.uploader._validate_project(project)
        self.assertTrue(any("does not exist" in e for e in errors))

    def test_validate_project_folder_exists(self) -> None:
        """Test validation passes when folder_path exists."""
        project = {
            "title": "Test title",
            "summary": "Test summary",
            "folder_path": str(self.temp_dir),
        }
        errors = self.uploader._validate_project(project)
        self.assertEqual(errors, [])

    def test_run_project_not_found(self) -> None:
        """Test run records error when project not found."""
        with patch("upload.UploadIssueReporter.record_error") as mock_record_error:
            self.uploader.run(9999)
            mock_record_error.assert_called_once()
            args = mock_record_error.call_args[0]
            self.assertEqual(args[0], 9999)
            self.assertIn("not found", args[1])

    def test_run_validation_fails(self) -> None:
        """Test run records errors when validation fails."""
        drpid = Storage.create_record("https://example.com/test")

        with patch("upload.UploadIssueReporter.record_error") as mock_record_error:
            self.uploader.run(drpid)
            self.assertTrue(mock_record_error.called)

    def test_get_field(self) -> None:
        """Test get_field returns trimmed value or empty string."""
        from utils.project_utils import get_field

        project = {"title": "  x  ", "missing": None}
        self.assertEqual(get_field(project, "title"), "x")
        self.assertEqual(get_field(project, "missing"), "")

    def test_agency_values_includes_both_when_different(self) -> None:
        """Distinct agency and office are both uploaded."""
        self.assertEqual(
            _agency_values_for_upload("DOT", "BTS"),
            ["DOT", "BTS"],
        )

    def test_agency_values_dedupes_when_office_matches_agency(self) -> None:
        """Same agency and office yields a single Government Agency entry."""
        self.assertEqual(
            _agency_values_for_upload(
                "Social Security Administration",
                "Social Security Administration",
            ),
            ["Social Security Administration"],
        )
        self.assertEqual(
            _agency_values_for_upload("SSA", "ssa"),
            ["SSA"],
        )

    def test_agency_values_handles_blank_and_whitespace(self) -> None:
        """Empty or whitespace-only fields are omitted."""
        self.assertEqual(_agency_values_for_upload("", ""), [])
        self.assertEqual(_agency_values_for_upload("  Agency  ", "  "), ["Agency"])
        self.assertEqual(_agency_values_for_upload("", "Office"), ["Office"])

    @patch("upload.UploadIssueReporter.record_error")
    def test_warn_if_num_files_mismatch_records_when_differs(
        self, mock_record_error: MagicMock
    ) -> None:
        from utils.Errors import ProjectAbort

        reporter = UploadIssueReporter(42)
        with self.assertRaises(ProjectAbort):
            _warn_if_num_files_mismatch(reporter, {"num_files": 3}, 2)
        mock_record_error.assert_called_once()
        self.assertEqual(mock_record_error.call_args[0][0], 42)
        msg = mock_record_error.call_args[0][1]
        self.assertIn("Upload batch count (2)", msg)
        self.assertIn("num_files from collection (3)", msg)

    @patch("upload.UploadIssueReporter.record_error")
    def test_warn_if_num_files_mismatch_skips_when_match(
        self, mock_record_error: MagicMock
    ) -> None:
        reporter = UploadIssueReporter(1)
        _warn_if_num_files_mismatch(reporter, {"num_files": 2}, 2)
        mock_record_error.assert_not_called()

    @patch("upload.UploadIssueReporter.record_error")
    def test_warn_if_num_files_skips_when_num_files_null(
        self, mock_record_error: MagicMock
    ) -> None:
        reporter = UploadIssueReporter(1)
        _warn_if_num_files_mismatch(reporter, {}, 2)
        mock_record_error.assert_not_called()

    def test_warn_if_num_files_mismatch_persists_to_storage(self) -> None:
        from utils.Errors import ProjectAbort

        drpid = Storage.create_record("https://example.com/test")
        Storage.update_record(drpid, {"num_files": 5})
        reporter = UploadIssueReporter(drpid)
        with self.assertRaises(ProjectAbort):
            _warn_if_num_files_mismatch(reporter, Storage.get(drpid), 3)
        record = Storage.get(drpid)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertIn("Upload batch count (3)", record.get("errors") or "")

    @patch("upload.UploadIssueReporter.record_error")
    def test_warn_if_num_files_mismatch_skips_zip_import(
        self, mock_record_error: MagicMock
    ) -> None:
        """ZIP uploads do not compare batch count to collected num_files."""
        reporter = UploadIssueReporter(1)
        _warn_if_num_files_mismatch(
            reporter, {"num_files": 12}, 1, used_zip=True
        )
        mock_record_error.assert_not_called()

    @patch("upload.UploadIssueReporter.record_error")
    def test_warn_if_num_files_mismatch_skips_large_file_partial_upload(
        self, mock_record_error: MagicMock
    ) -> None:
        """Large-file num_files includes catalog files that were not downloaded."""
        reporter = UploadIssueReporter(426)
        _warn_if_num_files_mismatch(
            reporter,
            {"num_files": 4, "status": "collected - large file"},
            1,
        )
        mock_record_error.assert_not_called()

    @patch("upload.DataLumosUploader.Storage")
    @patch.object(DataLumosUploader, "_upload_project", return_value="12345")
    def test_run_sets_uploaded_status(
        self,
        mock_upload_project: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        mock_storage.get.return_value = {
            "title": "T",
            "summary": "S",
            "status": "collected",
            "source_url": "",
        }
        uploader = DataLumosUploader()
        uploader._session = MagicMock()
        uploader.run(7)
        mock_upload_project.assert_called_once()
        call_args = mock_upload_project.call_args[0]
        self.assertEqual(call_args[1], 7)
        self.assertIsInstance(call_args[2], UploadIssueReporter)
        mock_storage.update_record.assert_called_with(
            7,
            {"datalumos_id": "12345", "status": "uploaded"},
        )
        uploader._session.close.assert_not_called()

    def test_close_closes_the_shared_browser(self) -> None:
        """The batch closes the browser once, not after every project."""
        self.uploader._session = MagicMock()
        self.uploader.close()
        self.uploader._session.close.assert_called_once()

    @patch("upload.DataLumosUploader.Storage")
    @patch.object(DataLumosUploader, "_upload_project", return_value="12345")
    def test_run_sets_uploaded_large_file_status(
        self,
        mock_upload_project: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        mock_storage.get.return_value = {
            "title": "T",
            "summary": "S",
            "status": "collected - large file",
            "source_url": "",
        }
        uploader = DataLumosUploader()
        uploader._session = MagicMock()
        uploader.run(7)
        mock_storage.update_record.assert_called_with(
            7,
            {"datalumos_id": "12345", "status": "uploaded - large file"},
        )


    def test_default_upload_saves_id_before_metadata(self) -> None:
        """The deposit API stores datalumos_id before posting the rest of the form."""
        order: list[str] = []
        project = {"title": "River gauges", "summary": "A set."}
        self.uploader._session = MagicMock()
        reporter = UploadIssueReporter(2501)

        def create(got_project: dict, got_reporter: UploadIssueReporter) -> str:
            order.append("create")
            self.assertEqual(got_project["title"], "River gauges")
            self.assertIs(got_reporter, reporter)
            return "259600"

        def save(drpid: int, fields: dict) -> None:
            order.append("save")
            self.assertEqual(drpid, 2501)
            self.assertEqual(fields, {"datalumos_id": "259600"})

        def fill(workspace_id: str, got_project: dict) -> None:
            order.append("fill")
            self.assertEqual(workspace_id, "259600")
            self.assertEqual(got_project["title"], "River gauges")

        with patch("upload.DepositProjectUpload.DepositProjectUpload") as deposit_cls:
            deposit = deposit_cls.return_value
            deposit.create.side_effect = create
            deposit.fill.side_effect = fill
            with patch("upload.DataLumosUploader.Storage.update_record", side_effect=save):
                result = self.uploader._upload_project(project, 2501, reporter)
        self.assertEqual(result, "259600")
        self.assertEqual(order, ["create", "save", "fill"])

    def test_ui_upload_uses_the_form(self) -> None:
        """--ui-upload keeps project creation on the browser form."""
        Args._config["upload_via_ui"] = True
        reporter = UploadIssueReporter(1)
        with patch.object(
            self.uploader, "_upload_project_via_form", return_value="9"
        ) as form_upload:
            with patch.object(self.uploader, "_upload_project_via_api") as api_upload:
                result = self.uploader._upload_project({}, 1, reporter)
        self.assertEqual(result, "9")
        form_upload.assert_called_once()
        api_upload.assert_not_called()

    def test_api_upload_posts_files_without_opening_the_project(self) -> None:
        """Files go out as deposit posts. The project page is not opened."""
        project = {
            "title": "River gauges",
            "summary": "A set.",
            "folder_path": str(self.temp_dir),
        }
        self.uploader._session = MagicMock()
        self.uploader._session.deposit_token = "jwt-saved"
        page = self.uploader._session.ensure_browser.return_value
        with patch("upload.DepositProjectUpload.DepositProjectUpload") as deposit_cls:
            deposit_cls.return_value.create.return_value = "42"
            with patch("upload.DataLumosUploader.Storage.update_record"):
                with patch("upload.DepositFileUpload.DepositFileUpload") as file_cls:
                    self.uploader._upload_project(project, 1, UploadIssueReporter(1))
        page.goto.assert_not_called()
        file_cls.assert_called_once_with(page, "jwt-saved")
        file_cls.return_value.upload_folder.assert_called_once_with("42", str(self.temp_dir))

    def test_later_project_reuses_the_saved_deposit_token(self) -> None:
        """The second project sends the token saved from the first."""
        project = {"title": "River gauges", "summary": "A set."}
        self.uploader._session = MagicMock()
        self.uploader._session.deposit_token = "jwt-from-first-project"
        with patch("upload.DepositProjectUpload.DepositProjectUpload") as deposit_cls:
            deposit_cls.return_value.create.return_value = "9"
            deposit_cls.return_value.token = "jwt-from-first-project"
            with patch("upload.DataLumosUploader.Storage.update_record"):
                result = self.uploader._upload_project(project, 1, UploadIssueReporter(1))
        self.assertEqual(result, "9")
        self.assertEqual(
            deposit_cls.call_args.kwargs["token"],
            "jwt-from-first-project",
        )
        self.uploader._session.keep_deposit_token.assert_called_once_with(
            "jwt-from-first-project"
        )

    def test_rejected_deposit_call_signs_in_and_retries_once(self) -> None:
        """A 401 signs in and posts the project a second time."""
        project = {"title": "River gauges", "summary": "A set."}
        self.uploader._session = MagicMock()
        self.uploader._session.deposit_token = "jwt-old"
        with patch("upload.DepositProjectUpload.DepositProjectUpload") as deposit_cls:
            deposit = deposit_cls.return_value
            deposit.create.side_effect = [
                RuntimeError("Deposit POST /deposit/createProject failed (401)"),
                "9",
            ]
            deposit.token = "jwt-new"
            with patch("upload.DataLumosUploader.Storage.update_record"):
                result = self.uploader._upload_project(project, 1, UploadIssueReporter(1))
        self.assertEqual(result, "9")
        self.uploader._session.reauthenticate.assert_called_once()
        self.assertEqual(deposit.create.call_count, 2)

    def test_file_count_mismatch_stops_before_create(self) -> None:
        """A disk count that differs from num_files does not create a project."""
        (self.temp_dir / "only.txt").write_text("x", encoding="utf-8")
        project = {
            "title": "River gauges",
            "summary": "A set.",
            "folder_path": str(self.temp_dir),
            "num_files": 3,
        }
        self.uploader._session = MagicMock()
        with patch("upload.DepositProjectUpload.DepositProjectUpload") as deposit_cls:
            with self.assertRaises(ProjectAbort):
                self.uploader._upload_project(project, 1, UploadIssueReporter(1))
        deposit_cls.assert_not_called()
        self.uploader._session.ensure_browser.assert_not_called()


class TestDataLumosUploaderValidation(unittest.TestCase):
    """Additional validation tests."""

    def setUp(self) -> None:
        """Set up test environment."""
        sys.argv = ["test", "upload"]
        Args._initialized = False
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.uploader = DataLumosUploader()
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        """Clean up after tests."""
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_validate_project_folder_is_file(self) -> None:
        """Test validation fails when folder_path is a file, not directory."""
        test_file = self.temp_dir / "test_file.txt"
        test_file.write_text("test")

        project = {
            "title": "Test title",
            "summary": "Test summary",
            "folder_path": str(test_file),
        }
        errors = self.uploader._validate_project(project)
        self.assertTrue(any("not a directory" in e for e in errors))

    def test_validate_project_empty_strings_treated_as_missing(self) -> None:
        """Test that empty strings are treated as missing values."""
        project = {"title": "", "summary": ""}
        errors = self.uploader._validate_project(project)
        self.assertIn("Missing required field: title", errors)
        self.assertIn("Missing required field: summary", errors)


if __name__ == "__main__":
    unittest.main()
