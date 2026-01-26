"""
Unit tests for Orchestrator.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from orchestration.Orchestrator import Orchestrator


class TestOrchestrator(unittest.TestCase):
    """Test cases for Orchestrator."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore argv after each test."""
        sys.argv = self._original_argv

    def test_run_unknown_module_raises(self) -> None:
        """Test run() with unknown module raises ValueError with valid modules listed."""
        with self.assertRaises(ValueError) as cm:
            Orchestrator.run("unknown")
        self.assertIn("unknown", str(cm.exception))
        self.assertIn("noop", str(cm.exception))
        self.assertIn("sourcing", str(cm.exception))
        self.assertIn("collectors", str(cm.exception))

    @patch("storage.Storage")
    @patch("sourcing.Sourcing.Sourcing")
    def test_run_sourcing_calls_sourcing_run(
        self, mock_sourcing_cls: MagicMock, mock_storage_cls: MagicMock
    ) -> None:
        """Test run("sourcing") instantiates Sourcing and calls run(-1)."""
        mock_storage = MagicMock()
        mock_storage_cls.initialize.return_value = mock_storage
        mock_storage_cls.get_instance.return_value = mock_storage
        mock_sourcing_instance = MagicMock()
        mock_sourcing_cls.return_value = mock_sourcing_instance
        
        # Also patch at orchestrator import level
        with patch("orchestration.Orchestrator.Storage", mock_storage_cls):
            Orchestrator.run("sourcing")

        mock_storage_cls.initialize.assert_called_once()
        mock_sourcing_cls.assert_called_once()
        mock_sourcing_instance.run.assert_called_once()
        mock_sourcing_instance.run.assert_called_with(-1)

    @patch("storage.Storage")
    @patch("collectors.SocrataCollector.SocrataCollector")
    def test_run_collectors_appends_error_when_run_raises(
        self, mock_collector_cls: MagicMock, mock_storage_cls: MagicMock
    ) -> None:
        """Test run("collectors") appends to errors when run() raises, and continues."""
        sys.argv = ["test", "noop"]
        Args._initialized = False
        Args.initialize()

        mock_storage = MagicMock()
        mock_storage.list_eligible_projects.return_value = [
            {"DRPID": 1, "source_url": "https://example.com"}
        ]
        mock_storage_cls.initialize.return_value = mock_storage
        # Mock direct method access via metaclass
        mock_storage_cls.list_eligible_projects = mock_storage.list_eligible_projects
        mock_storage_cls.append_to_field = mock_storage.append_to_field
        
        # Mock collector to raise NotImplementedError
        mock_collector_instance = MagicMock()
        mock_collector_instance.run.side_effect = NotImplementedError("collectors run not yet implemented")
        mock_collector_cls.return_value = mock_collector_instance
        
        # Also patch at orchestrator import level
        with patch("orchestration.Orchestrator.Storage", mock_storage_cls):
            Orchestrator.run("collectors")

        mock_storage_cls.initialize.assert_called_once()
        mock_storage.list_eligible_projects.assert_called_once_with("sourcing", None)
        mock_collector_cls.assert_called_once()
        mock_collector_instance.run.assert_called_once_with(1)
        mock_storage.append_to_field.assert_called()
        calls = [
            c
            for c in mock_storage.append_to_field.call_args_list
            if c[0][1] == "errors"
        ]
        self.assertGreaterEqual(len(calls), 1)
        self.assertIn("not yet implemented", str(calls[0]))
