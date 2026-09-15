"""phase.concept.template_select.prompt_candidate_enumerate — template candidate list.

concept.template.select 图节点 1:typed ``AgentState`` → ``tuple[str, ...]``
(候选 template_id 列表)(ADR-0220 §4.1)。

P3 骨架:返回静态占位三选一 (``react_prompt`` / ``routing_prompt`` /
``hierarchical_prompt``);真实 selector 由 ``PromptTemplateSelector``
provider 在 P4/P5 接管,此节点仅为 graph skeleton。
"""

from __future__ import annotations

from dataclasses import dataclass

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
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

# P3 placeholder candidates. Real selector logic lives in
# ``PromptTemplateSelector`` provider (ADR-0220 P4/P5).
_CANDIDATE_TUPLE: tuple[str, ...] = (
    "react_prompt",
    "routing_prompt",
    "hierarchical_prompt",
)


@dataclass(frozen=True, slots=True)
class PromptCandidateEnumerateExecutor:
    """concept.template.select 节点 1:state → tuple of template_id candidates."""

    semantic_name: str = "prompt.candidate.enumerate"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("state",)
    declared_outputs: tuple[PortName, ...] = ("candidates",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """prompt.candidate.enumerate 入口。

        inputs 端口(yaml):state (AgentState)
        outputs 端口(yaml):candidates (tuple[str, ...])

        P3 placeholder:恒返 ``_CANDIDATE_TUPLE``,不看 state。
        """
        del context
        del input
        return NodeOutput(port_values={"candidates": _CANDIDATE_TUPLE})


@plugin(
    id="phase.concept.template_select.prompt_candidate_enumerate",
    Config=None,
    provides=("concept::prompt.candidate.enumerate",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_concept_template_select_prompt_candidate_enumerate.checked",
                "phase_concept_template_select_prompt_candidate_enumerate.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = PromptCandidateEnumerateExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["PromptCandidateEnumerateExecutor", "setup"]
