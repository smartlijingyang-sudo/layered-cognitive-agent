"""Cordis plugin wiring — registers the typed prompt-section set.

The brain prompt is composed entirely from typed section providers. Each
section is a small class implementing ``PureSection`` or ``StatefulSection``;
the assembler walks a ``PromptTemplate``'s ``SectionReference`` list and
resolves each section through the ``PromptSectionRegistry``.

Sections live in one Cordis plugin (instead of one plugin per section)
because the design rule is **one plugin id per profile-managed unit of
work**, not one plugin id per data class. Each section is a declarative
instance, the plugin's job is to register them all. Profile YAML can still
toggle per-section Config keys to customise the text.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import PROMPT_SECTION_REGISTRY
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.prompts.sections import text as _text
from lca.plugins.prompts.sections import vocal as _vocal
from lca.plugins.prompts.sections.base import _ToolsConfig
from lca.plugins.prompts.sections.context import (
    build_autonomous_presets,
    build_context,
    build_home,
    build_user_profile,
)
from lca.plugins.prompts.sections.evidence import build_evidence_pack
from lca.plugins.prompts.sections.member_status import build_member_status
from lca.plugins.prompts.sections.memory import (
    build_memory_retrieval,
    build_privacy_firewall,
)
from lca.plugins.prompts.sections.role import (
    build_backstory_section,
    build_goal_section,
    build_role_section,
)
from lca.plugins.prompts.sections.runtime_env import (
    build_developer_timestamp,
    build_runtime_env,
)
from lca.plugins.prompts.sections.skills import (
    build_activated_skills,
    build_skill_duty,
)
from lca.plugins.prompts.sections.task import build_task
from lca.plugins.prompts.sections.teammates import (
    build_assigned_roles,
    build_member_reports,
    build_teammates,
)
from lca.plugins.prompts.sections.text import (
    build_hierarchical_instructions,
    build_react_tool_usage,
    build_react_workflow,
    build_routing_instructions,
)
from lca.plugins.prompts.sections.time import build_current_date
from lca.plugins.prompts.sections.tools import (
    build_available_skills_section,
    build_cloud_sandbox_section,
    build_tools_section,
)
from lca.plugins.prompts.sections.vocal import build_vocal_contract


class Config(BaseModel):
    """Profile-driven per-section overrides.

    The default block texts are baked in. Profiles can override any
    instruction block via ``instruction_overrides: {name: text}`` —
    the section plugin then uses the overridden text verbatim.
    """

    model_config = ConfigDict(extra="forbid")
    instruction_overrides: dict[str, str] = {}


@plugin(
    id="lca-brain-prompt-sections",
    Config=Config,
    provides=[],
    requires=[PROMPT_SECTION_REGISTRY.key],
    layer="L1",
    effects="none",
    description="Provide the typed prompt sections (pure + stateful).",
    test_suite="tests/architecture/test_prompt_section_registry.py",
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G5_COGNITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-brain-prompt-sections.checked",
                "lca-brain-prompt-sections.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register every section in the closed typed set.

    The assembler resolves ``available_skills`` through the active
    ``BrainPromptCatalog`` at render time. Tools come from the turn's
    ``tools`` argument, the same sequence the LLM request carries as
    native schemas.
    """

    registry = ctx.require(PROMPT_SECTION_REGISTRY.key)

    # Apply per-section overrides to the static instruction blocks.
    overrides = dict(config.instruction_overrides)
    # ADR-0248 声带契约文本覆盖（profile YAML 可定制）。
    if "vocal_contract" in overrides:
        _vocal._VOCAL_CONTRACT_TEXT = overrides["vocal_contract"]
    if "reply_first_reminder" in overrides:
        _vocal._REPLY_FIRST_TEXT = overrides["reply_first_reminder"]
    if "react_tool_usage_guidelines_gated" in overrides:
        _text._REACT_TOOL_USAGE_TEXT_GATED = overrides["react_tool_usage_guidelines_gated"]

    # Pull catalog providers lazily so the section plugin does not
    # require the catalog at setup time — composition root order is
    # independent of which section plugin loads first.
    from lca.contracts.capabilities import BRAIN_PROMPT_CATALOG_FACTORY, cap_key
    from lca.contracts.protocols.think.cognition import BrainPromptCatalogFactory
    from lca.plugins.composer.composition.skill_store import active_skill_store

    class _EmptyStore:
        def list_installed(self) -> tuple[object, ...]:
            return ()

    def _runtime_scope() -> object:
        inner_carrier = getattr(ctx, "_inner_carrier", None)
        if callable(inner_carrier):
            return inner_carrier()
        return ctx

    def _active_skill_store() -> object:
        """渲染期取与 Brain 工厂同源的 skill store（含 assistant Home 合并）。"""
        try:
            return active_skill_store(_runtime_scope())
        except Exception:
            return _EmptyStore()

    def _catalog_render(render_method: str) -> Callable[[], str]:
        sentinel = object()
        factory_key = cap_key(BRAIN_PROMPT_CATALOG_FACTORY)

        def _render() -> str:
            factory = ctx.soft_get(factory_key)
            if factory is None or not isinstance(factory, BrainPromptCatalogFactory):
                return ""
            try:
                catalog = factory.create(
                    skill_store=_active_skill_store(),  # type: ignore[arg-type]
                    tools=(),
                )
            except Exception:
                return ""
            method = getattr(catalog, render_method, sentinel)
            if method is sentinel or not callable(method):
                return ""
            try:
                return str(method())
            except Exception:
                return ""

        return _render

    # Pure sections
    pure_sections: list[tuple[str, object, str]] = [
        ("role", build_role_section(Config()), "static"),
        ("goal", build_goal_section(Config()), "static"),
        ("backstory", build_backstory_section(Config()), "static"),
        (
            "available_skills",
            build_available_skills_section(
                _ToolsConfig(), catalog=_catalog_render("render_brain_skills")
            ),
            "catalog_skills",
        ),
        ("react_workflow", build_react_workflow(Config()), "static"),
        ("react_tool_usage_guidelines", build_react_tool_usage(Config()), "static"),
        ("routing_instructions", build_routing_instructions(Config()), "static"),
        ("hierarchical_instructions", build_hierarchical_instructions(Config()), "static"),
        ("runtime_env", build_runtime_env(Config()), "static"),
        ("developer_timestamp", build_developer_timestamp(Config()), "static"),
    ]
    for name, section, _kind in pure_sections:
        registry.register(section, kind="pure", name=name)

    registry.register(build_tools_section(_ToolsConfig()), kind="stateful", name="tools")
    registry.register(
        build_cloud_sandbox_section(_ToolsConfig()), kind="stateful", name="cloud_sandbox"
    )
    stateful_sections: list[tuple[str, object]] = [
        ("current_date", build_current_date(Config())),
        ("task", build_task(Config())),
        ("activated_skills", build_activated_skills(Config())),
        ("context", build_context(Config())),
        ("user_profile", build_user_profile(Config())),
        ("home", build_home(Config())),
        ("autonomous_presets", build_autonomous_presets(Config())),
        ("memory_retrieval", build_memory_retrieval(Config())),
        ("skill_duty", build_skill_duty(Config())),
        ("privacy_firewall", build_privacy_firewall(Config())),
        ("teammates", build_teammates(Config())),
        ("assigned_roles_text", build_assigned_roles(Config())),
        ("member_reports_text", build_member_reports(Config())),
        ("member_status_text", build_member_status(Config())),
        ("evidence_pack_text", build_evidence_pack(Config())),
        ("vocal_contract", build_vocal_contract(Config())),
    ]
    for name, section in stateful_sections:
        registry.register(section, kind="stateful", name=name)


__all__ = ["Config", "setup"]
