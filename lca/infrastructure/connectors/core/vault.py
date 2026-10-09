"""Secure Connector Vault & User Isolation Storage (INV-01, INV-02)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from lca.infrastructure.connectors.core.state import ConnectionMetadata, ConnectionState
from lca.infrastructure.path.locator import get_lca_home


class ConnectorVaultError(RuntimeError):
    """Raised when the connector vault cannot be read or written honestly.

    A corrupt or unreadable ``connections.json`` must never degrade silently
    to "no connections" (RA-071): callers would act on a lie (e.g. re-prompt
    OAuth for a service the user already connected).
    """


def atomic_write_json(file_path: Path, data: dict[str, Any]) -> None:
    """Atomically writes JSON data using a temporary file and os.replace to prevent corruption."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = file_path.with_suffix(f".tmp.{time.time_ns()}")
    tmp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_file, file_path)


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

    def _load_raw_connections(self) -> list[dict[str, Any]]:
        user_file = self._get_user_connections_file()
        if not user_file.is_file():
            return []
        try:
            data = json.loads(user_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # RA-071: a present-but-unreadable vault file is a secret-access
            # failure. Degrading to [] would lie to every caller downstream.
            raise ConnectorVaultError(
                f"connector vault file is unreadable or corrupt: {user_file}"
            ) from exc
        if not isinstance(data, dict):
            raise ConnectorVaultError(
                f"connector vault file has an unexpected shape: {user_file}"
            )
        connections = data.get("connections", [])
        if not isinstance(connections, list):
            raise ConnectorVaultError(
                f"connector vault file has an unexpected shape: {user_file}"
            )
        return connections

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
            elif status_raw in ("REVOKED", "REAUTHORIZATION_REQUIRED"):
                state = ConnectionState.REAUTHORIZATION_REQUIRED
            else:
                state = ConnectionState.NOT_CONNECTED

            conn_id = item.get("connected_account_id") or item.get("connection_id")
            redirect_url = item.get("redirect_url") or item.get("auth_url")
            scopes = item.get("scopes", [])

            account_ident = item.get("account_identity") or item.get("account_id")
            result.append(
                ConnectionMetadata(
                    service=service,
                    account_id=str(item.get("account_id") or "default"),
                    state=state,
                    account_identity=str(account_ident) if account_ident else None,
                    connection_id=conn_id,
                    auth_url=redirect_url,
                    scopes=scopes,
                )
            )
        return result

    def get_connection(
        self, service: str, account_id: str = "default"
    ) -> ConnectionMetadata:
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

    def upsert_connection(
        self,
        service: str,
        state: ConnectionState,
        account_id: str = "default",
        account_identity: str | None = None,
        connection_id: str | None = None,
        auth_url: str | None = None,
        scopes: list[str] | None = None,
    ) -> ConnectionMetadata:
        raw_list = self._load_raw_connections()
        service_norm = service.lower().strip()
        updated = False
        new_row = {
            "identifier": service_norm,
            "status": state.value,
            "account_id": account_id,
            "account_identity": account_identity or account_id,
            "connection_id": connection_id,
            "auth_url": auth_url,
            "scopes": scopes or [],
            "updated_at": time.time(),
        }
        for i, item in enumerate(raw_list):
            if str(item.get("identifier") or item.get("app_slug") or "").lower().strip() == service_norm:
                raw_list[i] = new_row
                updated = True
                break
        if not updated:
            raw_list.append(new_row)
        atomic_write_json(self._get_user_connections_file(), {"connections": raw_list})
        return ConnectionMetadata(
            service=service_norm,
            account_id=account_id,
            state=state,
            account_identity=account_identity or account_id,
            connection_id=connection_id,
            auth_url=auth_url,
            scopes=scopes or [],
        )

    def list_active_services(self) -> list[str]:
        """Returns names of all services currently in ACTIVE state."""
        return [
            conn.service for conn in self.list_connections() if conn.state == ConnectionState.ACTIVE
        ]
