"""Tests for root-cause prompt invariant against text URLs and identity disclosure (INV-CONN-05)."""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.connectors.core.state import ConnectionState
from lca.infrastructure.connectors.core.vault import ConnectorVault
from lca.plugins.prompts.sections.connected_services import (
    render_connected_services_text,
)
from lca.plugins.prompts.sections.plugin import Config
from lca.plugins.prompts.sections.text import build_react_tool_usage
from lca.plugins.prompts.template_provider import _builtin_section_refs


def test_react_tool_usage_contains_dynamic_url_and_identity_iron_laws() -> None:
    """INV-CONN-05: System instructions must contain iron laws against fabricating dynamic URLs and requiring identity disclosure."""
    section = build_react_tool_usage(Config())
    text = section.text

    # Must contain prohibition of fabricating dynamic URLs
    assert "动态授权" in text or "授权" in text
    assert "严禁" in text or "必须调用" in text
    assert "动身份先报身份" in text or "账号身份" in text or "凭证" in text


def test_connected_services_renders_account_identity(tmp_path: Path) -> None:
    """INV-CONN-05: ConnectedServicesSection must display account identity for active services."""
    lca_home = tmp_path / ".lca"
    vault = ConnectorVault(user_id="alice", lca_home=lca_home)
    vault.upsert_connection(
        service="google-drive",
        state=ConnectionState.ACTIVE,
        account_identity="alice@gmail.com",
    )

    rendered = render_connected_services_text(vault=vault)
    assert "google-drive" in rendered
    assert "alice@gmail.com" in rendered


def test_connected_services_is_mounted_in_builtin_template() -> None:
    """INV-CONN-05: connected_services section must be part of built-in prompt template."""
    refs = _builtin_section_refs()
    names = [r[0] for r in refs]
    assert "connected_services" in names
