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
    from lca.plugins.transport.webserver.routes_1.routes_assistants.standing_files import (
        DEFAULT_STANDING_FILE_TEMPLATES,
    )

    section = build_react_tool_usage(Config())
    text = section.text

    # 身份披露铁律仍在 react_tool_usage_guidelines 段（fd53f1642 明确保留）
    assert "动身份先报身份" in text or "账号身份" in text or "凭证" in text

    # 动态 URL 铁律已迁入 CONSTITUTION.md 模板（fd53f1642：prompt 规则不许硬编码在 py），
    # section 不再承载；此处钉新家。注意：模板→backstory 组装预算截断问题另由
    # test_url_iron_rule_survives_standing_assembly（xfail strict, todo-40）钉住。
    constitution = DEFAULT_STANDING_FILE_TEMPLATES["CONSTITUTION.md"]
    assert "动态授权" in constitution
    assert "严禁" in constitution and "必须调用" in constitution


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
