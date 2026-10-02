"""Tests for Gmail Connector CLI & Manifest (INV-02, INV-03, INV-06)."""

from __future__ import annotations

import json
from pathlib import Path

from lca.infrastructure.connectors.core.state import ConnectionState
from lca.infrastructure.connectors.core.vault import ConnectorVault
from lca.infrastructure.connectors.gmail.cli import GmailConnectorCLI


def test_gmail_cli_status_not_connected(tmp_path: Path) -> None:
    vault = ConnectorVault(user_id="test_user", lca_home=tmp_path)
    cli = GmailConnectorCLI(vault=vault)

    res = cli.execute(["status"])
    assert res["status"] == "not_connected"
    assert res["appName"] == "Gmail"
    assert "authUrl" in res
    assert "connectionId" in res
    # INV-03: Must provide widget markup
    assert "[widget:connector_auth?" in res["widget"]


def test_gmail_cli_status_active(tmp_path: Path) -> None:
    user_conn_dir = tmp_path / "users" / "active_user" / "connectors"
    user_conn_dir.mkdir(parents=True)
    conn_file = user_conn_dir / "connections.json"
    conn_file.write_text(
        json.dumps(
            {
                "connections": [
                    {
                        "identifier": "gmail",
                        "connected_account_id": "ca_active_gmail",
                        "status": "ACTIVE",
                        "redirect_url": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    vault = ConnectorVault(user_id="active_user", lca_home=tmp_path)
    cli = GmailConnectorCLI(vault=vault)

    res = cli.execute(["status"])
    assert res["status"] == "active"
    assert res["connectionId"] == "ca_active_gmail"


def test_gmail_cli_accounts_list(tmp_path: Path) -> None:
    user_conn_dir = tmp_path / "users" / "multi_user" / "connectors"
    user_conn_dir.mkdir(parents=True)
    conn_file = user_conn_dir / "connections.json"
    conn_file.write_text(
        json.dumps(
            {
                "connections": [
                    {
                        "identifier": "gmail",
                        "account_id": "work",
                        "connected_account_id": "ca_work",
                        "status": "ACTIVE",
                    },
                    {
                        "identifier": "gmail",
                        "account_id": "personal",
                        "connected_account_id": "ca_personal",
                        "status": "AWAITING_AUTH",
                        "redirect_url": "https://auth.example.com",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    vault = ConnectorVault(user_id="multi_user", lca_home=tmp_path)
    cli = GmailConnectorCLI(vault=vault)

    res = cli.execute(["accounts"])
    assert len(res["accounts"]) == 2
    assert res["accounts"][0]["account_id"] == "work"
    assert res["accounts"][0]["state"] == ConnectionState.ACTIVE
    assert res["accounts"][1]["account_id"] == "personal"
    assert res["accounts"][1]["state"] == ConnectionState.AWAITING_AUTH


def test_gmail_cli_send_requires_upload_flag_inv06(tmp_path: Path) -> None:
    """INV-06: Two-phase write requires --upload staged file, rejects inline body."""
    vault = ConnectorVault(user_id="test_user", lca_home=tmp_path)
    cli = GmailConnectorCLI(vault=vault)

    # Attempting to call +send without --upload must be rejected
    res = cli.execute(["+send", "--to", "alice@example.com", "--subject", "Hello"])
    assert res["success"] is False
    assert "error" in res
    assert "--upload" in res["error"]


def test_gmail_cli_send_with_valid_upload_file(tmp_path: Path) -> None:
    vault = ConnectorVault(user_id="test_user", lca_home=tmp_path)
    cli = GmailConnectorCLI(vault=vault)

    draft_file = tmp_path / "draft.eml"
    draft_file.write_text("Dear Alice,\nThis is a verified test email.", encoding="utf-8")

    res = cli.execute(
        [
            "+send",
            "--to",
            "alice@example.com",
            "--subject",
            "Test Meeting",
            "--upload",
            str(draft_file),
        ]
    )
    assert res["success"] is True
    assert res["to"] == "alice@example.com"
    assert res["subject"] == "Test Meeting"
    assert "Dear Alice" in res["content_preview"]
