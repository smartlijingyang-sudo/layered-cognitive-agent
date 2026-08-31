"""CordisCreatorRole —— Creator §13.3 的人格画像（Tier-3 behavior）。

Plugin-thinking
---------------
本插件把 ``cordis-creator`` 角色固化为可被 boot 加载的 plugin 声明，
提供 :class:`RoleProfile` + :class:`ToolPermissionManifest` 数据；上层
``spawn_agent(role_profile=...)`` 直接消费，行为层无须重复。

Persona 文案遵循宪法 §13.1 + §13.2.4「HOST vs AGENT PRESET」区分，
allowed_tools 包含 ``cordis_control`` + ``file_write`` + ``bash`` 三个
creator 必备工具。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import CORDIS_CREATOR_ROLE
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.team.role_team import (
    RoleProfile,
    ToolPermissionManifest,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


PERSONA_GOAL = (
    "You are a coding agent powered by the {{model}} model. "
    "You can read and modify the runtime you run on.\n\n"
    "Two planes decide where an edit belongs:\n"
    "- HOST composition: process-global (persistence, sandbox, approval, model route)\n"
    "- AGENT PRESET: per-session (tools, persona, prompt sections)\n\n"
    "A service row belongs in HOST, or in PRESET behind an isolate scope. "
    "Presets you author live at $LCA_AGENT_PRESETS_HOME/<id>/ and auto-mount "
    "on the next boot of any session that loads the corresponding bundle.\n\n"
    "Two bundled skills ship with this persona — load them with activate_skill "
    "before authoring or editing a plugin or composition:\n"
    "- `cordis-plugin-development` — plugin_meta TypedDict, factory contract, "
    "PR12 + §23.2 invariants, cordis_control actions.\n"
    "- `editing-lca-compositions` — bundle YAML schema, preset directory "
    "layout, HOST vs PRESET plane decision, reducer/journal/capability "
    "constitutional boundaries."
)


# Constitutional invariants the persona must commit to (§13.3.6「self-improving
# boundary」).  Not enforced at runtime — only declared here for inspector /
# docs tooling to surface.
PERSONA_BOUNDARIES = (
    "Can inspect capability graph, mount/unmount plugins, write plugin sources, publish presets.",
    "Cannot hook agent.* to rewrite Decisions (C4).",
    "Cannot mutate AgentState directly (C4).",
    "Cannot widen capability grant (C5).",
    "Cannot skip PluginMeta TypedDict declaration (PR12).",
    "Cannot skip §23.2 invariant check.",
)


def build_cordis_creator_role_profile() -> RoleProfile:
    """返回 :class:`RoleProfile` —— 给 ``spawn_agent(role_profile=...)`` 使用。

    这里返回的不是 plugin metadata，而是数据；plugin 自身只声明存在，
    上层通过 ``ctx.require("role.cordis_creator")`` 取这份数据。
    """
    return RoleProfile(
        role="cordis-creator",
        goal=PERSONA_GOAL,
        backstory="",
        tool_permission_manifest=ToolPermissionManifest(
            allowed_tools=[
                "cordis_control",
                "file_write",
                "bash",
                "activate_skill",
                "read_skill_reference",
            ],
            max_calls_per_task={
                "cordis_control": 32,
                "file_write": 16,
                "bash": 16,
                "activate_skill": 8,
                "read_skill_reference": 8,
            },
            requires_approval=[],
        ),
        tone="concise",
        values=[
            "Plugin-thinking: every capability is a plugin.",
            "C3: every state change goes to journal.",
            "C4: Composer is composition-only; never touch Decision / AgentState.",
            "C5: mount grants ⊆ caller grant.",
            "PR12: every factory declares plugin_meta TypedDict.",
        ],
        extra={
            "persona_boundaries": list(PERSONA_BOUNDARIES),
            "preset_home_env": "LCA_AGENT_PRESETS_HOME",
        },
    )


@plugin(
    id="lca-role-cordis-creator",
    provides=[CORDIS_CREATOR_ROLE.key],
    requires=[],
    implements=["RoleProfile"],
    layer="L3",
    effects="none",
    description="Creator §13.3 cordis-creator role persona + tool permission manifest",
    test_suite="tests/test_cordis_creator_e2e.py",
    kind=PluginKind.PRIMITIVE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G8_COLLAB, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-role-cordis-creator.checked", "lca-role-cordis-creator.served")
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
    """把角色画像挂到 ``role.cordis_creator`` 的类型化 capability seam。"""
    del config
    ctx.provide(CORDIS_CREATOR_ROLE.key, build_cordis_creator_role_profile())


__all__ = [
    "PERSONA_BOUNDARIES",
    "PERSONA_GOAL",
    "Config",
    "build_cordis_creator_role_profile",
]
