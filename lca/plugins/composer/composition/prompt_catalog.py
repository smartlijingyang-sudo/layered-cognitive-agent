"""构造模型可见的技能与工具目录。

组合根只负责选择并装配能力；此模块负责将已解析的技能索引与工具
元数据投影为稳定的提示文本。它是提示目录的唯一渲染接缝，避免不同
组合路径各自读取技能存储或派生不一致的降级文本。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from lca.contracts.capabilities import BRAIN_PROMPT_CATALOG_FACTORY
from lca.contracts.protocols.memory.operational_skills import SkillIndexEntry, SkillPackageStore
from lca.contracts.protocols.runtime.infra import Tool
from lca.contracts.protocols.think.cognition import BrainPromptCatalog, BrainPromptCatalogFactory
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress

_EMPTY_SKILLS = "（无可用技能；可使用 search_skill 查找）"
_EMPTY_BRAIN_SKILLS = "（无可用技能）"
_EMPTY_TOOLS = "（无可用工具）"


@dataclass(frozen=True)
class ModelPromptCatalog:
    """一份已解析的、模型可见的技能与工具目录。

    ``load`` 只在组合期读取一次 ``SkillPackageStore``；其余方法都是纯渲染，
    从而让模型提示中的目录在一个 Agent 图内保持一致。存储读取失败不降级为
    伪空目录，而是由组合根明确失败，避免生产配置与模型可见能力漂移。
    """

    installed_skills: tuple[SkillIndexEntry, ...]
    tools: tuple[Tool, ...] = ()

    @classmethod
    def load(
        cls,
        skill_store: SkillPackageStore,
        *,
        tools: Iterable[Tool] = (),
    ) -> ModelPromptCatalog:
        """从已选择的存储接缝创建不可变提示目录。"""
        return cls(installed_skills=skill_store.list_installed(), tools=tuple(tools))

    @classmethod
    def for_tools(cls, tools: Iterable[Tool]) -> ModelPromptCatalog:
        """为仅需要工具目录的兼容调用创建无技能目录。"""
        return cls(installed_skills=(), tools=tuple(tools))

    def render_skill_discovery(self) -> str:
        """渲染包含摘要与版本的技能发现目录。"""
        lines = tuple(
            f"- {skill.skill_id}: {skill.name} — {skill.summary} (v{skill.version})"
            for skill in self.installed_skills
        )
        return "\n".join(lines) or _EMPTY_SKILLS

    def render_brain_skills(self) -> str:
        """渲染提供给 Brain 工厂的紧凑技能目录。"""
        lines = tuple(f"- {skill.skill_id}: {skill.name}" for skill in self.installed_skills)
        return "\n".join(lines) or _EMPTY_BRAIN_SKILLS

    def render_tools_xml(self) -> str:
        """渲染稳定的 XML-like 工具目录。"""
        lines = tuple(
            f'<tool name="{tool.name}">{tool.description or tool.name}</tool>'
            for tool in self.tools
        )
        return "\n".join(lines) or _EMPTY_TOOLS


class DefaultBrainPromptCatalogFactory(BrainPromptCatalogFactory):
    """Freeze the selected skills and Agent-local tools into a default catalog."""

    def create(
        self,
        *,
        skill_store: SkillPackageStore,
        tools: Iterable[Tool],
    ) -> BrainPromptCatalog:
        """Build the one immutable prompt view consumed by a Brain factory."""

        return ModelPromptCatalog.load(skill_store, tools=tools)


class Config(BaseModel):
    """Strict configuration for the built-in Brain prompt catalog primitive."""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-brain-prompt-catalog-default",
    Config=Config,
    provides=[BRAIN_PROMPT_CATALOG_FACTORY.key],
    requires=[],
    implements=[BrainPromptCatalogFactory],
    layer="L1",
    effects="none",
    description="Provide the profile-selected skills and tools catalog for Brain factories.",
    test_suite="tests/architecture/test_brain_prompt_catalog_capability.py",
    kind=PluginKind.PRIMITIVE,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-brain-prompt-catalog-default.checked', 'lca-brain-prompt-catalog-default.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: BaseModel) -> None:
    """Expose the default catalog factory without selecting ambient composition state."""

    del config
    ctx.provide(BRAIN_PROMPT_CATALOG_FACTORY.key, DefaultBrainPromptCatalogFactory())


__all__ = [
    "Config",
    "DefaultBrainPromptCatalogFactory",
    "ModelPromptCatalog",
    "setup",
]
