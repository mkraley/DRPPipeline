"""Obtain a Globus refresh token for adc_globus_collector (one-time setup)."""

from __future__ import annotations

import sys
from typing import Any

try:
    import globus_sdk
except ImportError as exc:
    raise SystemExit("Install globus-sdk: pip install globus-sdk") from exc

TRANSFER_RESOURCE_SERVER = "transfer.api.globus.org"
TRANSFER_SCOPES = "urn:globus:auth:scope:transfer.api.globus.org:all"


def extract_transfer_refresh_token(tokens: Any) -> str:
    """
    Extract the transfer refresh token from a globus-sdk v4 token response.

    Args:
        tokens: Response from ``oauth2_exchange_code_for_tokens``.

    Returns:
        Refresh token string for ``transfer.api.globus.org``.

    Raises:
        SystemExit: When no refresh token is present in the response.
    """
    by_rs = tokens.by_resource_server
    transfer_data = by_rs.get(TRANSFER_RESOURCE_SERVER)
    if transfer_data and transfer_data.get("refresh_token"):
        return str(transfer_data["refresh_token"])

    for token_data in by_rs.values():
        if token_data.get("refresh_token"):
            return str(token_data["refresh_token"])

    raise SystemExit(
        "No refresh token returned. Re-run with a fresh auth code and ensure "
        "oauth2_start_flow(refresh_tokens=True) is used."
    )


def main() -> None:
    """Run native-app login flow and print refresh token."""
    client_id = input("Globus native app client ID: ").strip()
    if not client_id:
        raise SystemExit("Client ID is required")

    client = globus_sdk.NativeAppAuthClient(client_id=client_id)
    client.oauth2_start_flow(requested_scopes=TRANSFER_SCOPES, refresh_tokens=True)
    authorize_url = client.oauth2_get_authorize_url()
    print("\nOpen this URL in a browser, log in, and authorize:\n")
    print(authorize_url)
    print()
    auth_code = input("Paste the authorization code here: ").strip()
    tokens = client.oauth2_exchange_code_for_tokens(auth_code)
    refresh_token = extract_transfer_refresh_token(tokens)
    print("\nAdd to config.json:\n")
    print(f'  "globus_client_id": "{client_id}",')
    print(f'  "globus_refresh_token": "{refresh_token}",')
    print('  "globus_destination_endpoint_id": "<your GCP collection UUID>",')
    print('  "globus_destination_base_path": "/~/"')


if __name__ == "__main__":
    main()
