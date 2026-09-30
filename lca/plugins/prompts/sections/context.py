"""Context, user-profile, home, and autonomous-preset sections."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from pydantic import BaseModel

from lca.cognition.brain.sections.types import (
    block,
    context_exclusions_for,
    join_lines,
    label_line,
    memory_records_from_manifest,
    render_artifacts_block,
    render_context_lines,
    render_subtasks_block,
)
from lca.contracts.atoms.enums.enums import MemoryCategory
from lca.contracts.models.cognition.prompt_assembly import SectionOutput
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra.infra import Tool
from lca.infrastructure.preset.discovery import AssistantPresetDiscovery


class ContextSection:
    name: ClassVar[str] = "context"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        task: str,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        del role_profile, task, tools, activated_skills
        exclude = context_exclusions_for(awareness)
        body = join_lines(
            [
                render_context_lines(
                    manifest,
                    exclude_kinds=exclude,
                    exclude_categories=frozenset(
                        {MemoryCategory.IDENTITY, MemoryCategory.PREFERENCE}
                    ),
                ),
                render_subtasks_block(manifest),
                render_artifacts_block(manifest),
            ]
        )
        return SectionOutput(text=label_line("CONTEXT", body))


class UserProfileSection:
    """Render the structured user profile from identity/preference memories.

    ADR-0246 PR-5: the model sees a distilled USER_PROFILE block (称呼/身份/
    偏好) independent of raw memory lines. Empty profile renders nothing so
    the section disappears until the first identity/preference fact lands.
    """

    name: ClassVar[str] = "user_profile"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        task: str,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        del role_profile, task, awareness, tools, activated_skills
        records = memory_records_from_manifest(manifest)
        identity = [r.content for r in records if r.category is MemoryCategory.IDENTITY]
        preference = [r.content for r in records if r.category is MemoryCategory.PREFERENCE]
        lines: list[str] = []
        if identity:
            lines.append("身份：" + "；".join(identity))
        if preference:
            lines.append("偏好：" + "；".join(preference))
        if not lines:
            return SectionOutput(text="")
        return SectionOutput(text=label_line("USER_PROFILE", "\n".join(lines)))


class HomeSection:
    """Render the assistant Home paths for a bound run (ADR-0242 D3/D5).

    The model needs to know where its persistent memory, skills, and
    workspace live so it stops searching the sandbox root. Renders nothing
    for unbound runs.
    """

    name: ClassVar[str] = "home"

    # 声明式行模板：每条 ``(key, template)`` 一行，渲染时用动态值 format。
    # 改文案/加行只动这张表，不碰控制流（数据驱动，对齐 prompt 模板范式）。
    _LINE_TEMPLATES: tuple[tuple[str, str], ...] = (
        ("assistant_id", "assistant_id: {assistant_id}"),
        ("home_dir", "home_dir: {home}"),
        (
            "memory_dir",
            "memory_dir: {home}/memory/  (持久化记忆；系统自动写入，勿用沙箱命令访问)",
        ),
        ("skills_dir", "skills_dir: {home}/skills/"),
        ("presets_dir", "presets_dir: {home}/presets/  (自主创造的预置包目录)"),
        ("plugins_dir", "plugins_dir: {home}/plugins/  (自主创造的插件独立执行目录)"),
        (
            "workspace_dir",
            "workspace_dir: {home}/workspace/  (沙箱 /mnt/data 映射到此)",
        ),
        (
            "routing",
            "目录路由: 用户问「你的目录/配置/记忆/你自己」时，默认用 home_dir；"
            "只有文件操作/代码执行/生成产物时才用 workspace_dir（沙箱 /mnt/data）。",
        ),
        (
            "memory_note",
            "记忆说明: 用户让你记住的偏好/事实由系统自动写入 memory_dir，"
            "也可用 memory_search / memory_add / memory_update / memory_remove 读写；"
            "下次会话会自动带到你的上下文。",
        ),
    )

    # 依赖 ``home`` 才渲染的 key；``assistant_id`` 单独判断。
    _HOME_ONLY_KEYS: frozenset[str] = frozenset(
        {
            "home_dir",
            "memory_dir",
            "skills_dir",
            "presets_dir",
            "plugins_dir",
            "workspace_dir",
            "routing",
            "memory_note",
        }
    )

    def render(
        self,
        *,
        role_profile: RoleProfile,
        task: str,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        del task, awareness, manifest, tools, activated_skills
        extra = getattr(role_profile, "extra", {}) or {}
        home = str(extra.get("assistant_home_path") or "").strip()
        assistant_id = str(extra.get("assistant_id") or "").strip()
        if not home and not assistant_id:
            return SectionOutput(text="")
        lines = [
            template.format(home=home, assistant_id=assistant_id)
            for key, template in self._LINE_TEMPLATES
            if (key == "assistant_id" and assistant_id) or (key in self._HOME_ONLY_KEYS and home)
        ]
        return SectionOutput(text=block("HOME", "\n".join(lines)))


class AutonomousPresetsSection:
    """Renders the autonomous custom presets and tools discovered in the assistant's Home."""

    name: ClassVar[str] = "autonomous_presets"

    def render(
        self,
        *,
        role_profile: RoleProfile,
        task: str,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput:
        del task, awareness, manifest, tools, activated_skills
        extra = getattr(role_profile, "extra", {}) or {}
        home = str(extra.get("assistant_home_path") or "").strip()
        if not home:
            return SectionOutput(text="")

        overview = AssistantPresetDiscovery(home).render_prompt_overview()
        if not overview:
            return SectionOutput(text="")
        return SectionOutput(text=block("autonomous_presets", overview))


def build_context(config: BaseModel) -> ContextSection:
    del config
    return ContextSection()


def build_user_profile(config: BaseModel) -> UserProfileSection:
    del config
    return UserProfileSection()


def build_home(config: BaseModel) -> HomeSection:
    del config
    return HomeSection()


def build_autonomous_presets(config: BaseModel) -> AutonomousPresetsSection:
    del config
    return AutonomousPresetsSection()


__all__ = [
    "AutonomousPresetsSection",
    "ContextSection",
    "HomeSection",
    "UserProfileSection",
    "build_autonomous_presets",
    "build_context",
    "build_home",
    "build_user_profile",
]
