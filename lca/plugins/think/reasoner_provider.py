"""phase.think.reasoner — PromptReasoner instance provider for inner think subgraph.

把 :class:`LLMResolver` 解析出的 :class:`LLMAdapter` 绑定到
:class:`PromptReasoner` 单例,注册到 ``reasoner`` capability 键。
think 子图三个 reason 节点(``plan`` / ``render`` / ``complete``)通过
``context.runtime.reasoner`` 读这个实例,duck-typed 调
``build_turn_plan`` / ``render_turn`` / ``complete_turn``。

与 ``lca.plugins.reasoner.prompt`` 的关系(同名 seam 不同形态):

- ``reasoner.prompt``(:class:`PromptReasoner` **class**):外层
  :class:`SimpleBrainFactory` 用 ``reasoner_cls=`` per-call 实例化。
- 本 plugin(``reasoner``,**instance**):内层 think subgraph 跨节点复用,
  LLMAdapter / RoleProfile 在 boot 时绑一次。

boundary:

- 本 plugin 负责 LLMResolver → PromptReasoner 的接线;凭据加载与 provider
  fallback 归 ``llm_resolver`` plugin。
- role profile 故意最小(assistant);真实 prompt 内容由 prompt assembler
  与 template selector 在每次 turn 决定。
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
from lca.contracts.mechanisms.capability.capability import require_capability
from lca.contracts.protocols import Reasoner
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="phase.think.reasoner",
    provides=("reasoner",),
    requires=("llm_resolver",),
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
        reads=("llm_resolver",),
        emits=("reasoner.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Bind LLMResolver adapter to PromptReasoner; register ``reasoner`` capability."""
    del config
    from lca.cognition.brain.reasoner.reasoner import PromptReasoner
    from lca.contracts.models.team.role.team import (
        RoleProfile,
        ToolPermissionManifest,
    )

    llm_resolver = require_capability(ctx, "llm_resolver")
    adapter = llm_resolver.resolve()
    role_profile = RoleProfile(
        role="assistant",
        goal="answer user questions",
        backstory="LCA inner think subgraph reasoner",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    ctx.provide("reasoner", PromptReasoner(llm=adapter, role_profile=role_profile))


__all__ = ["Config", "setup"]
