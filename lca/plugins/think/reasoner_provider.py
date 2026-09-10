"""phase.think.reasoner — PromptReasoner instance provider for inner think subgraph.

构造 :class:`PromptReasoner` 单例并注册到 ``reasoner`` capability 键。
think 子图三个 reason 节点(``plan`` / ``render`` / ``complete``)通过
``context.runtime.reasoner`` 读这个实例,duck-typed 调
``build_turn_plan`` / ``render_turn`` / ``complete_turn``。

LLM 凭证与 adapter 装配由 ``ProductionLLMResolver`` 在 framework
层完成,本 plugin 直接从环境/Profile 读取 ``default_model``,不再
依赖外部 ``llm_resolver`` capability。

与 ``lca.plugins.reasoner.prompt`` 的关系(同名 seam 不同形态):

- ``reasoner.prompt``(:class:`PromptReasoner` **class**):外层
  :class:`SimpleBrainFactory` 用 ``reasoner_cls=`` per-call 实例化。
- 本 plugin(``reasoner``,**instance**):内层 think subgraph 跨节点复用,
  LLMAdapter / RoleProfile 在 boot 时绑一次。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols import Reasoner
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.llm.resolver import ProductionLLMResolver


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    default_model: str | None = None


@plugin(
    id="phase.think.reasoner",
    provides=("reasoner",),
    requires=(),
    implements=[Reasoner],
    layer="L1",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide a configured PromptReasoner instance for the inner "
        "think subgraph. Built from the active LLMResolver adapter."
    ),
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
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
                "phase_think_reasoner.checked",
                "phase_think_reasoner.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("reasoner.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Resolve LLM adapter and bind it to PromptReasoner; register ``reasoner`` capability."""
    from lca.cognition.brain.reasoner.reasoner import PromptReasoner
    from lca.contracts.models.team.role.team import (
        RoleProfile,
        ToolPermissionManifest,
    )

    adapter = ProductionLLMResolver(default_model=config.default_model).resolve()
    role_profile = RoleProfile(
        role="assistant",
        goal="answer user questions",
        backstory="LCA inner think subgraph reasoner",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    ctx.provide("reasoner", PromptReasoner(llm=adapter, role_profile=role_profile))


__all__ = ["Config", "setup"]
