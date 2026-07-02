"""Shared Globus configuration helpers for ADC supplemental modules."""

from __future__ import annotations

from collectors.GlobusTransferService import GlobusTransferService
from utils.Args import Args


def build_transfer_service(*, require_destination: bool = True) -> GlobusTransferService:
    """
    Construct ``GlobusTransferService`` from ``Args`` configuration.

    Args:
        require_destination: When True, ``globus_destination_endpoint_id`` is required.

    Returns:
        Configured transfer service instance.

    Raises:
        RuntimeError: When required Globus settings are missing from config.
    """
    client_id = getattr(Args, "globus_client_id", None)
    refresh_token = getattr(Args, "globus_refresh_token", None)
    destination_endpoint_id = getattr(Args, "globus_destination_endpoint_id", None)
    if not client_id or not refresh_token:
        raise RuntimeError(
            "Globus config missing: set globus_client_id and globus_refresh_token in config.json"
        )
    if require_destination and not destination_endpoint_id:
        raise RuntimeError(
            "Globus config missing: set globus_destination_endpoint_id in config.json"
        )
    base_path = str(getattr(Args, "globus_destination_base_path", "/~/") or "/~/")
    poll_timeout = float(getattr(Args, "globus_transfer_poll_timeout_sec", 3600) or 3600)
    return GlobusTransferService(
        client_id=str(client_id),
        refresh_token=str(refresh_token),
        destination_endpoint_id=str(destination_endpoint_id or ""),
        destination_base_path=base_path,
        poll_timeout_sec=poll_timeout,
    )
