"""create_assistant from_role integration tests.

验证从角色档案创建助理的完整链路：
1. from_role → RoleCard 解析 → SOUL.md 用 backstory 填充
2. profile.json 携带 role_id 和卡片 emoji
3. manifest.json 携带 role_id
4. catalog.get() 返回的 AssistantSpec.role_id 正确
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import pytest

from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.contracts.protocols.assistant.role_resolver import (
    RoleCard,
    RoleNotFoundError,
)
from lca.plugins.domain.assistant.catalog.plugin import AssistantCatalogImpl


class _StubRoleResolver:
    """Test double: resolves two role_ids."""

    _CARDS: ClassVar[dict[str, RoleCard]] = {
        "engineering/architect": RoleCard(
            role_id="engineering/architect",
            title="软件架构师",
            department="engineering",
            summary="系统设计专家",
            backstory="# 软件架构师\n\n你是系统架构专家，精通领域驱动设计。\n\n## 核心规则\n- 先理解现状再设计\n- 最小改动原则",
            emoji="🏛️",
        ),
        "design/ux": RoleCard(
            role_id="design/ux",
            title="UX 设计师",
            department="design",
            summary="用户体验设计",
            backstory="# UX 设计师\n\n你关注用户体验与交互设计。",
            emoji="🎨",
        ),
    }

    def resolve(self, role_id: str) -> RoleCard:
        if role_id not in self._CARDS:
            raise RoleNotFoundError(f"unknown: {role_id}")
        return self._CARDS[role_id]

    def list_available(self) -> tuple[str, ...]:
        return tuple(sorted(self._CARDS))


@pytest.fixture
def catalog(tmp_path: Path) -> AssistantCatalogImpl:
    return AssistantCatalogImpl(
        root=tmp_path / "assistants",
        role_resolver=_StubRoleResolver(),
    )


class TestCreateFromRole:
    def test_from_role_fills_soul_with_backstory(self, catalog: AssistantCatalogImpl) -> None:
        handle = catalog.create(
            CreateAssistantRequest(
                name="小架",
                description="架构顾问",
                from_role="engineering/architect",
            )
        )
        soul = (Path(handle.home_path) / "SOUL.md").read_text(encoding="utf-8")
        assert "系统架构专家" in soul
        assert "领域驱动设计" in soul
        assert "{{ name }}" not in soul

    def test_from_role_sets_emoji_in_profile(self, catalog: AssistantCatalogImpl) -> None:
        handle = catalog.create(
            CreateAssistantRequest(
                name="小架",
                description="架构顾问",
                from_role="engineering/architect",
            )
        )
        profile = json.loads((Path(handle.home_path) / "profile.json").read_text(encoding="utf-8"))
        assert profile["emoji"] == "🏛️"
        assert profile["role_id"] == "engineering/architect"

    def test_from_role_stored_in_manifest(self, catalog: AssistantCatalogImpl) -> None:
        handle = catalog.create(
            CreateAssistantRequest(
                name="小架",
                description="架构顾问",
                from_role="engineering/architect",
            )
        )
        manifest = json.loads(
            (Path(handle.home_path) / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["role_id"] == "engineering/architect"

    def test_spec_carries_role_id(self, catalog: AssistantCatalogImpl) -> None:
        handle = catalog.create(
            CreateAssistantRequest(
                name="小架",
                description="架构顾问",
                from_role="engineering/architect",
            )
        )
        spec = catalog.get(handle.assistant_id)
        assert spec.role_id == "engineering/architect"

    def test_without_from_role_has_no_role_id(self, catalog: AssistantCatalogImpl) -> None:
        handle = catalog.create(CreateAssistantRequest(name="通用", description="通用助理"))
        spec = catalog.get(handle.assistant_id)
        assert spec.role_id is None

    def test_from_role_unknown_raises(self, catalog: AssistantCatalogImpl) -> None:
        with pytest.raises(Exception, match="unknown"):
            catalog.create(
                CreateAssistantRequest(
                    name="假",
                    from_role="nonexistent/role",
                )
            )

    def test_from_role_without_resolver_raises(self, tmp_path: Path) -> None:
        catalog_no_resolver = AssistantCatalogImpl(root=tmp_path / "assistants")
        with pytest.raises(Exception, match="RoleCardResolver"):
            catalog_no_resolver.create(
                CreateAssistantRequest(name="假", from_role="engineering/architect")
            )

    def test_spec_agent_profile_has_real_persona(self, catalog: AssistantCatalogImpl) -> None:
        handle = catalog.create(
            CreateAssistantRequest(
                name="小架",
                description="架构顾问",
                from_role="engineering/architect",
            )
        )
        spec = catalog.get(handle.assistant_id)
        profile = spec.agent_spec.profile
        assert profile.role == "小架"
        assert "架构" in profile.goal or "架构" in profile.backstory
        assert "系统架构专家" in profile.backstory

    def test_from_role_design_card(self, catalog: AssistantCatalogImpl) -> None:
        handle = catalog.create(
            CreateAssistantRequest(
                name="小设",
                description="UX 设计师",
                from_role="design/ux",
            )
        )
        soul = (Path(handle.home_path) / "SOUL.md").read_text(encoding="utf-8")
        assert "用户体验" in soul
        profile = json.loads((Path(handle.home_path) / "profile.json").read_text(encoding="utf-8"))
        assert profile["emoji"] == "🎨"

    def test_soul_overrides_from_role_backstory(self, catalog: AssistantCatalogImpl) -> None:
        """ADR-0242 D1：soul 非空时覆盖角色卡 backstory，但 role_id 仍进 manifest。"""
        soul = (
            "## 🧠 身份\n"
            + "你是自定义架构助理。" * 20
            + "\n## 🎭 性格\n"
            + "结论先行。" * 20
            + "\n## 🛠 能力\n"
            + "擅长系统设计。" * 20
            + "\n## 🗣 语气\n"
            + "专业务实。" * 20
        )
        handle = catalog.create(
            CreateAssistantRequest(
                name="小架",
                description="架构顾问",
                from_role="engineering/architect",
                soul=soul,
            )
        )
        written = (Path(handle.home_path) / "SOUL.md").read_text(encoding="utf-8")
        assert written.startswith(soul)
        for marker in ("## 🔒 安全边界", "## 💾 记忆规则", "## ⚠️ 错误处理", "## 🚫 红线"):
            assert marker in written
        manifest = json.loads(
            (Path(handle.home_path) / "manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["role_id"] == "engineering/architect"

    def test_from_role_goals_from_mission_section(self, catalog: AssistantCatalogImpl) -> None:
        """ADR-0242 D2：从角色卡「核心使命」段提取前 3 个目标写入 goals.yaml。"""
        import yaml

        class _MissionResolver(_StubRoleResolver):
            _CARDS: ClassVar[dict[str, RoleCard]] = {
                "engineering/architect": RoleCard(
                    role_id="engineering/architect",
                    title="软件架构师",
                    department="engineering",
                    summary="系统设计专家",
                    backstory=(
                        "# 软件架构师\n\n"
                        "## 核心使命\n"
                        "### 系统设计\n"
                        "### 架构评审\n"
                        "### 技术选型\n"
                        "### 性能优化\n"
                    ),
                    emoji="🏛️",
                ),
            }

        cat = AssistantCatalogImpl(
            root=catalog._root,
            role_resolver=_MissionResolver(),
        )
        handle = cat.create(
            CreateAssistantRequest(
                name="小架",
                from_role="engineering/architect",
            )
        )
        goals = yaml.safe_load((Path(handle.home_path) / "goals.yaml").read_text(encoding="utf-8"))
        names = [g["name"] for g in goals["goals"]]
        assert names == ["系统设计", "架构评审", "技术选型"]
