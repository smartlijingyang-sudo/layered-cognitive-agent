"""Tests for user-scoped SSOT vault isolation without global fallback (INV-CONN-01)."""

from __future__ import annotations

import json
from pathlib import Path

from lca.infrastructure.connectors.core.state import ConnectionState
from lca.infrastructure.connectors.core.vault import ConnectorVault
from lca.infrastructure.integrations.composio.settings.settings import (
    ComposioSettings,
    resolve_user_connections_path,
)


def test_new_user_has_empty_connectors_even_if_legacy_global_exists(tmp_path: Path) -> None:
    """INV-CONN-01: A new user must have an empty connector list, without inheriting legacy global files."""
    lca_home = tmp_path / ".lca"
    
    # Simulate existing legacy global file with active credentials
    legacy_file = lca_home / "composio" / "connections.json"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text(
        json.dumps({
            "connections": [
                {
                    "identifier": "google-drive",
                    "status": "ACTIVE",
                    "label": "Google Drive",
                    "account_identity": "legacy_admin@gmail.com",
                }
            ]
        }),
        encoding="utf-8",
    )
    
    # Instantiate vault for brand new user
    new_user_vault = ConnectorVault(user_id="brand-new-user-456", lca_home=lca_home)
    
    # Must be 100% clean and empty
    connections = new_user_vault.list_connections()
    assert connections == [], "New user must NOT inherit legacy global connectors!"
    assert new_user_vault.list_active_services() == []
    conn = new_user_vault.get_connection("google-drive")
    assert conn is not None
    assert conn.state == ConnectionState.NOT_CONNECTED


def test_user_connections_path_resolution(tmp_path: Path) -> None:
    """INV-CONN-01: Path resolver must return user-scoped connections.json."""
    lca_home = tmp_path / ".lca"
    path = resolve_user_connections_path(user_id="alice", lca_home=lca_home)
    assert path == lca_home / "users" / "alice" / "connectors" / "connections.json"


def test_user_vault_write_and_read_isolation(tmp_path: Path) -> None:
    """INV-CONN-01: Two users have strictly isolated connector states."""
    lca_home = tmp_path / ".lca"
    
    user1_vault = ConnectorVault(user_id="user-1", lca_home=lca_home)
    user2_vault = ConnectorVault(user_id="user-2", lca_home=lca_home)
    
    user1_vault.upsert_connection(
        service="gmail",
        account_id="u1_acc",
        state=ConnectionState.ACTIVE,
        account_identity="user1@example.com",
    )
    
    # User 1 has gmail
    assert "gmail" in user1_vault.list_active_services()
    u1_conn = user1_vault.get_connection("gmail")
    assert u1_conn is not None
    assert u1_conn.account_identity == "user1@example.com"
    
    # User 2 is completely isolated and empty
    assert user2_vault.list_active_services() == []
    u2_conn = user2_vault.get_connection("gmail")
    assert u2_conn is not None
    assert u2_conn.state == ConnectionState.NOT_CONNECTED
