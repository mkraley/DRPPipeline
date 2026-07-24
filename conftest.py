"""
Pytest configuration: isolate tests from repo config.json and real data folders.

When pytest loads this module, ``DRP_PYTEST_CONFIG`` is set to a generated config
whose ``base_output_dir`` lives under a temporary directory. Tests that call
``Args.initialize()`` therefore use ``TEST######`` folders in temp space instead
of paths like ``C:\\DataRescue\\AHRQData\\AHRQ000007``.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="drp_pytest_"))
(_TEST_ROOT / "output").mkdir(parents=True, exist_ok=True)
_TEST_CONFIG_PATH = _TEST_ROOT / "pytest_config.json"
_TEST_CONFIG_PATH.write_text(
    json.dumps(
        {
            "base_output_dir": str(_TEST_ROOT / "output"),
            "google_sheet_name": "TEST",
            "db_path": str(_TEST_ROOT / "pytest.db"),
        }
    ),
    encoding="utf-8",
)
os.environ.setdefault("DRP_PYTEST_CONFIG", str(_TEST_CONFIG_PATH))


@pytest.fixture(autouse=True)
def _reset_args_before_each_test() -> None:
    """Ensure each test can reload Args from the pytest config, not config.json."""
    from utils.Args import Args

    Args.reset_for_tests()
    yield
    Args.reset_for_tests()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Remove the session-scoped pytest output directory."""
    shutil.rmtree(_TEST_ROOT, ignore_errors=True)
    os.environ.pop("DRP_PYTEST_CONFIG", None)
