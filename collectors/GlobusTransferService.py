"""
Globus Transfer API helper for ADC supplemental collection.

Uses a refresh token and destination Globus Connect Personal endpoint to
transfer public USDA share paths into local project folders.
"""

from __future__ import annotations

import time
from typing import Any

from collectors.GlobusPathInventory import GlobusInventorySummary, GlobusPathInventory
from utils.Logger import Logger

try:
    import globus_sdk
except ImportError:  # pragma: no cover - exercised when dependency missing
    globus_sdk = None  # type: ignore[assignment]

TERMINAL_TASK_STATES = frozenset({"SUCCEEDED", "FAILED", "INACTIVE"})


class GlobusTransferService:
    """Submit and monitor Globus transfers between collections."""

    def __init__(
        self,
        *,
        client_id: str,
        refresh_token: str,
        destination_endpoint_id: str,
        destination_base_path: str = "/~/",
        poll_interval_sec: float = 10.0,
        poll_timeout_sec: float = 3600.0,
    ) -> None:
        """
        Initialize the Globus transfer service.

        Args:
            client_id: Globus native-app client ID.
            refresh_token: OAuth refresh token with transfer scopes.
            destination_endpoint_id: Local Globus Connect Personal collection UUID.
            destination_base_path: Base path on the destination endpoint (POSIX).
            poll_interval_sec: Seconds between task status polls.
            poll_timeout_sec: Max seconds to wait for transfer completion.
        """
        self._client_id = client_id
        self._refresh_token = refresh_token
        self._destination_endpoint_id = destination_endpoint_id
        self._destination_base_path = self._normalize_base_path(destination_base_path)
        self._poll_interval_sec = poll_interval_sec
        self._poll_timeout_sec = poll_timeout_sec
        self._transfer_client: Any | None = None

    def list_source_entries(
        self,
        source_endpoint_id: str,
        source_path: str,
    ) -> list[dict[str, Any]]:
        """
        List directory entries at a source path.

        Args:
            source_endpoint_id: Globus collection UUID for the source.
            source_path: Directory path on the source collection.

        Returns:
            List of entry dicts from ``operation_ls``.
        """
        client = self._get_transfer_client()
        response = client.operation_ls(source_endpoint_id, path=source_path)
        return list(response)

    def summarize_remote_path(
        self,
        source_endpoint_id: str,
        source_path: str,
    ) -> GlobusInventorySummary:
        """
        Recursively inventory file counts and total bytes at a source path.

        Args:
            source_endpoint_id: Globus collection UUID for the source.
            source_path: Directory path on the source collection.

        Returns:
            Aggregate inventory for the directory tree.
        """
        inventory = GlobusPathInventory(self.list_source_entries)
        summary = inventory.summarize(source_endpoint_id, source_path)
        Logger.info(
            "Globus inventory %s:%s -> %s files, %s dirs, %s bytes",
            source_endpoint_id,
            summary.root_path,
            summary.file_count,
            summary.dir_count,
            summary.total_bytes,
        )
        return summary

    def transfer_directory(
        self,
        *,
        source_endpoint_id: str,
        source_path: str,
        destination_relative_path: str,
        label: str,
    ) -> str:
        """
        Recursively transfer a source directory to the configured destination.

        Args:
            source_endpoint_id: Globus source collection UUID.
            source_path: Source directory path.
            destination_relative_path: Path under ``destination_base_path``.
            label: Globus task label.

        Returns:
            Globus task ID for the submitted transfer.
        """
        dest_path = self._join_endpoint_path(
            self._destination_base_path,
            destination_relative_path,
        )
        task_data = globus_sdk.TransferData(
            source_endpoint=source_endpoint_id,
            destination_endpoint=self._destination_endpoint_id,
            label=label,
            sync_level="checksum",
        )
        task_data.add_item(source_path, dest_path, recursive=True)
        client = self._get_transfer_client()
        result = client.submit_transfer(task_data)
        task_id = str(result["task_id"])
        Logger.info(
            "Globus transfer submitted task_id=%s src=%s dst=%s",
            task_id,
            source_path,
            dest_path,
        )
        return task_id

    def wait_for_task(self, task_id: str) -> str:
        """
        Poll until a transfer task reaches a terminal state.

        Args:
            task_id: Globus transfer task ID.

        Returns:
            Final task status string (e.g. ``SUCCEEDED``).

        Raises:
            RuntimeError: When the task fails or polling times out.
        """
        client = self._get_transfer_client()
        deadline = time.monotonic() + self._poll_timeout_sec
        while time.monotonic() < deadline:
            task = client.get_task(task_id)
            status = str(task.get("status") or "")
            if status in TERMINAL_TASK_STATES:
                if status != "SUCCEEDED":
                    raise RuntimeError(
                        f"Globus transfer {task_id} ended with status {status}"
                    )
                Logger.info("Globus transfer %s succeeded", task_id)
                return status
            time.sleep(self._poll_interval_sec)
        raise RuntimeError(
            f"Globus transfer {task_id} did not complete within {self._poll_timeout_sec}s"
        )

    @staticmethod
    def _normalize_base_path(base_path: str) -> str:
        """Ensure destination base path starts with / and ends with /."""
        path = base_path.strip() or "/~/"
        if not path.startswith("/"):
            path = f"/{path}"
        if not path.endswith("/"):
            path = f"{path}/"
        return path

    @staticmethod
    def _join_endpoint_path(base_path: str, relative_path: str) -> str:
        """Join POSIX paths on a Globus endpoint."""
        rel = relative_path.strip("/").replace("\\", "/")
        return f"{base_path}{rel}/" if rel else base_path

    def _get_transfer_client(self) -> Any:
        """Return a cached TransferClient authorized via refresh token."""
        if self._transfer_client is not None:
            return self._transfer_client
        if globus_sdk is None:
            raise RuntimeError(
                "globus-sdk is not installed. Add globus-sdk to requirements.txt."
            )
        auth_client = globus_sdk.NativeAppAuthClient(client_id=self._client_id)
        authorizer = globus_sdk.RefreshTokenAuthorizer(
            self._refresh_token,
            auth_client,
        )
        self._transfer_client = globus_sdk.TransferClient(authorizer=authorizer)
        return self._transfer_client
