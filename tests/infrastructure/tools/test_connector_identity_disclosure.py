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


def test_react_tool_usage_contains_dynamic_url_and_identity_iron_laws(
    tmp_path: Path,
) -> None:
    """INV-CONN-05: System instructions must contain iron laws against fabricating dynamic URLs and requiring identity disclosure."""
    from lca.infrastructure.memory.contextfiles.service.assembly import (
        refresh_standing_backstory,
    )

    section = build_react_tool_usage(Config())
    text = section.text

    # 身份披露铁律仍在 react_tool_usage_guidelines 段
    # （fd53f1642 明确保留；5098195a0 改为英文措辞，语义不变）
    assert "Identity first" in text or "account identity" in text

    # 动态 URL 铁律已迁出 repo（fd53f1642→CONSTITUTION.md；5098195a0→Tier-1
    # PLATFORM.md 部署文件，不在 repo 内）。此处用铁律原文同构内容验证机制：
    # platform tier 整段注入 backstory、零截断——以何种载体部署，模型必见整段。
    # 部署漂移风险（新机器无 PLATFORM.md 则铁律缺席）见 backlog P1 todo-41。
    platform_root = tmp_path / "lca_home"
    platform_root.mkdir()
    (platform_root / "PLATFORM.md").write_text(
        "- 动态授权与第三方连接严禁在文本中拼装 URL，所有连接与授权必须调用官方工具生成。\n",
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()
    out = refresh_standing_backstory(str(home), "", platform_root=platform_root)
    assert "严禁在文本中拼装 URL" in out
    assert "必须调用官方工具生成" in out


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
