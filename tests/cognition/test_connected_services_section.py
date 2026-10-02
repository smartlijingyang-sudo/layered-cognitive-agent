"""Tests for ConnectedServicesSection prompt injection (INV-01, INV-02)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from lca.contracts.models.team.role.team import RoleProfile
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
        json.dumps({
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
        }),
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
    mock_vault.list_active_services.return_value = ["gmail", "googledrive"]

    section = ConnectedServicesSection(vault=mock_vault)
    role_profile = MagicMock(spec=RoleProfile)
    out = section.render(role_profile=role_profile, tools=[])

    assert "## Connected External Services" in out.text
    assert "- gmail (status: ACTIVE)" in out.text
    assert "- googledrive (status: ACTIVE)" in out.text
