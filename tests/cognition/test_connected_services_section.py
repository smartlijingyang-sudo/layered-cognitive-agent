"""Tests for ConnectedServicesSection prompt injection (INV-01, INV-02)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from lca.contracts.models.team.role.team import RoleProfile
from lca.infrastructure.connectors.core.state import (
    ConnectionMetadata,
    ConnectionState,
)
from lca.infrastructure.connectors.core.vault import ConnectorVault
from lca.plugins.prompts.sections.connected_services import (
    ConnectedServicesSection,
    render_connected_services_text,
)


def test_render_connected_services_with_active_integrations(tmp_path: Path) -> None:
    # Prepare dummy active connections
    user_conn_dir = tmp_path / "users" / "test_user" / "connectors"
    user_conn_dir.mkdir(parents=True)
    conn_file = user_conn_dir / "connections.json"
    conn_file.write_text(
        json.dumps(
            {
                "connections": [
                    {
                        "identifier": "gmail",
                        "status": "ACTIVE",
                        "connected_account_id": "ca_gmail",
                    },
                    {
                        "identifier": "github",
                        "status": "ACTIVE",
                        "connected_account_id": "ca_github",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    vault = ConnectorVault(user_id="test_user", lca_home=tmp_path)
    text = render_connected_services_text(vault=vault)

    assert "## Connected External Services" in text
    assert "- gmail (status: ACTIVE)" in text
    assert "- github (status: ACTIVE)" in text
    # INV-01: Must not leak tokens
    assert "token" not in text.lower()


def test_render_connected_services_empty(tmp_path: Path) -> None:
    vault = ConnectorVault(user_id="empty_user", lca_home=tmp_path)
    text = render_connected_services_text(vault=vault)

    assert "## Connected External Services" in text
    assert "No external services are currently connected" in text


def test_connected_services_section_render() -> None:
    mock_vault = MagicMock()
    # a0f9809ce switched the render path from vault.list_active_services()
    # (service name strings) to vault.list_connections() (ConnectionMetadata
    # with is_active); the mock must follow the new seam.
    mock_vault.list_connections.return_value = [
        ConnectionMetadata(service="gmail", state=ConnectionState.ACTIVE),
        ConnectionMetadata(service="googledrive", state=ConnectionState.ACTIVE),
    ]

    section = ConnectedServicesSection(vault=mock_vault)
    role_profile = MagicMock(spec=RoleProfile)
    out = section.render(role_profile=role_profile, tools=[])

    assert "## Connected External Services" in out.text
    assert "- gmail (status: ACTIVE)" in out.text
    assert "- googledrive (status: ACTIVE)" in out.text


def test_render_connected_services_budget_truncation() -> None:
    mock_vault = MagicMock()
    # 7 active services (mock the post-a0f9809ce list_connections() seam)
    mock_vault.list_connections.return_value = [
        ConnectionMetadata(service=svc, state=ConnectionState.ACTIVE)
        for svc in ["gmail", "github", "googledrive", "slack", "notion", "linear", "jira"]
    ]

    # Max 5 services allowed in budget
    text = render_connected_services_text(vault=mock_vault, max_services=5)
    assert "- github (status: ACTIVE)" in text
    assert "- gmail (status: ACTIVE)" in text
    assert "- googledrive (status: ACTIVE)" in text
    assert "- jira (status: ACTIVE)" in text
    assert "- linear (status: ACTIVE)" in text
    # 2 services folded into summary
    assert "- ... and 2 more active services" in text
    # Ensure notion/slack are folded out of the top 5
    assert "- notion (status: ACTIVE)" not in text
