"""Secure Connector Vault & User Isolation Storage (INV-01, INV-02)."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from lca.infrastructure.connectors.core.state import ConnectionMetadata, ConnectionState
from lca.infrastructure.path.locator import get_lca_home


class ConnectorVault:
    """Safely manages connector connections for a specific user.

    Guarantees INV-01: OAuth tokens are strictly retained in backend secure storage,
    and only metadata (service, account_id, state, connection_id, auth_url, scopes)
    is exposed to callers.
    """

    def __init__(self, user_id: str = "lca-local-user", lca_home: Path | None = None) -> None:
        self._user_id = user_id
        self._lca_home = lca_home or get_lca_home()

    @property
    def user_id(self) -> str:
        return self._user_id

    def _get_user_connections_file(self) -> Path:
        return self._lca_home / "users" / self._user_id / "connectors" / "connections.json"

    def _get_composio_connections_file(self) -> Path:
        return self._lca_home / "composio" / "connections.json"

    def _load_raw_connections(self) -> list[dict[str, Any]]:
        user_file = self._get_user_connections_file()
        if user_file.is_file():
            with contextlib.suppress(Exception):
                data = json.loads(user_file.read_text(encoding="utf-8"))
                return data.get("connections", [])

        # Fallback to shared composio file if user-specific file is not present
        composio_file = self._get_composio_connections_file()
        if composio_file.is_file():
            with contextlib.suppress(Exception):
                data = json.loads(composio_file.read_text(encoding="utf-8"))
                return data.get("connections", [])

        return []

    def list_connections(self) -> list[ConnectionMetadata]:
        raw_list = self._load_raw_connections()
        result: list[ConnectionMetadata] = []
        for item in raw_list:
            service = str(item.get("identifier") or item.get("app_slug") or "").lower().strip()
            if not service:
                continue
            status_raw = str(item.get("status") or "").upper()
            if status_raw in ("ACTIVE", "CONNECTED"):
                state = ConnectionState.ACTIVE
            elif status_raw in ("AWAITING_AUTH", "PENDING", "INITIATED"):
                state = ConnectionState.AWAITING_AUTH
            elif status_raw in ("EXPIRED", "TOKEN_EXPIRED"):
                state = ConnectionState.TOKEN_EXPIRED
            elif status_raw in ("RATE_LIMITED",):
                state = ConnectionState.RATE_LIMITED
            else:
                state = ConnectionState.NOT_CONNECTED

            conn_id = item.get("connected_account_id") or item.get("connection_id")
            redirect_url = item.get("redirect_url") or item.get("auth_url")
            scopes = item.get("scopes", [])

            result.append(
                ConnectionMetadata(
                    service=service,
                    account_id=str(item.get("account_id") or "default"),
                    state=state,
                    connection_id=conn_id,
                    auth_url=redirect_url,
                    scopes=scopes,
                )
            )
        return result

    def get_connection(
        self, service: str, account_id: str = "default"
    ) -> ConnectionMetadata | None:
        service_norm = service.lower().strip()
        connections = self.list_connections()
        for conn in connections:
            if conn.service == service_norm and conn.account_id == account_id:
                return conn
        for conn in connections:
            if conn.service == service_norm:
                return conn

        # Return NOT_CONNECTED stub if unknown
        return ConnectionMetadata(
            service=service_norm,
            account_id=account_id,
            state=ConnectionState.NOT_CONNECTED,
            connection_id=None,
            auth_url=None,
        )

    def list_active_services(self) -> list[str]:
        """Returns names of all services currently in ACTIVE state."""
        return [
            conn.service for conn in self.list_connections() if conn.state == ConnectionState.ACTIVE
        ]
