"""Tests for Connector Safe Vault & User Isolation (INV-01, INV-02)."""

from __future__ import annotations

import json
from pathlib import Path

from lca.infrastructure.connectors.core.state import ConnectionState
from lca.infrastructure.connectors.core.vault import ConnectorVault


def test_connector_vault_reads_from_user_dir(tmp_path: Path) -> None:
    # Set up user directory: ~/.lca/users/u123/connectors/connections.json
    user_conn_dir = tmp_path / "users" / "u123" / "connectors"
    user_conn_dir.mkdir(parents=True)
    conn_file = user_conn_dir / "connections.json"
    conn_file.write_text(
        json.dumps(
            {
                "connections": [
                    {
                        "identifier": "gmail",
                        "connected_account_id": "ca_u123_gmail",
                        "status": "ACTIVE",
                        "redirect_url": None,
                    },
                    {
                        "identifier": "github",
                        "connected_account_id": "ca_u123_gh",
                        "status": "AWAITING_AUTH",
                        "redirect_url": "https://backend.composio.dev/auth/gh",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    vault = ConnectorVault(user_id="u123", lca_home=tmp_path)
    conns = vault.list_connections()
    assert len(conns) == 2

    gmail = vault.get_connection("gmail")
    assert gmail is not None
    assert gmail.service == "gmail"
    assert gmail.state == ConnectionState.ACTIVE
    assert gmail.connection_id == "ca_u123_gmail"
    assert gmail.auth_url is None

    github = vault.get_connection("github")
    assert github is not None
    assert github.service == "github"
    assert github.state == ConnectionState.AWAITING_AUTH
    assert github.connection_id == "ca_u123_gh"
    assert github.auth_url == "https://backend.composio.dev/auth/gh"

    active_services = vault.list_active_services()
    assert active_services == ["gmail"]


def test_connector_vault_fallback_to_composio(tmp_path: Path) -> None:
    # User dir does not exist, but composio/connections.json exists
    comp_dir = tmp_path / "composio"
    comp_dir.mkdir(parents=True)
    conn_file = comp_dir / "connections.json"
    conn_file.write_text(
        json.dumps(
            {
                "connections": [
                    {
                        "identifier": "slack",
                        "connected_account_id": "ca_slack_fallback",
                        "status": "ACTIVE",
                        "redirect_url": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    vault = ConnectorVault(user_id="new_user", lca_home=tmp_path)
    slack = vault.get_connection("slack")
    assert slack is not None
    assert slack.service == "slack"
    assert slack.state == ConnectionState.ACTIVE
    assert slack.connection_id == "ca_slack_fallback"


def test_connector_vault_returns_not_connected_for_unknown_service(tmp_path: Path) -> None:
    vault = ConnectorVault(user_id="u1", lca_home=tmp_path)
    meta = vault.get_connection("notion")
    assert meta is not None
    assert meta.service == "notion"
    assert meta.state == ConnectionState.NOT_CONNECTED
    assert meta.connection_id is None


def test_connector_vault_parses_revoked_as_reauthorization_required(tmp_path: Path) -> None:
    user_conn_dir = tmp_path / "users" / "revoked_user" / "connectors"
    user_conn_dir.mkdir(parents=True)
    conn_file = user_conn_dir / "connections.json"
    conn_file.write_text(
        json.dumps(
            {
                "connections": [
                    {
                        "identifier": "google-drive",
                        "status": "REVOKED",
                        "connected_account_id": "ca_revoked",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    vault = ConnectorVault(user_id="revoked_user", lca_home=tmp_path)
    drive = vault.get_connection("google-drive")
    assert drive is not None
    assert drive.state == ConnectionState.REAUTHORIZATION_REQUIRED


def test_atomic_write_json(tmp_path: Path) -> None:
    from lca.infrastructure.connectors.core.vault import atomic_write_json

    target = tmp_path / "test_dir" / "data.json"
    payload = {"status": "ok", "count": 42}
    atomic_write_json(target, payload)

    assert target.is_file()
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == payload
