"""phase.concept.template_select.prompt_candidate_score — template candidate scoring.

concept.template.select 图节点 2:typed ``tuple[str, ...]`` + state →
``tuple[tuple[str, float], ...]``(ADR-0220 §4.1)。

P3 骨架:所有 candidate score = 1.0(无差别 ranking);真实 scoring 在
``PromptTemplateSelector`` provider(P4/P5)接管。
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
from lca.contracts.models.core.state.state import AgentState
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


@dataclass(frozen=True, slots=True)
class PromptCandidateScoreExecutor:
    """concept.template.select 节点 2:candidates → scored candidates."""

    semantic_name: str = "prompt.candidate.score"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("candidates", "state")
    declared_outputs: tuple[PortName, ...] = ("scored",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """prompt.candidate.score 入口。

        inputs 端口(yaml):candidates (tuple[str, ...]), state (AgentState)
        outputs 端口(yaml):scored (tuple[tuple[str, float], ...])

        P3 placeholder:所有 candidate score = 1.0。
        """
        del context
        candidates = input.port_values.get("candidates")
        if candidates is None:
            candidates = ()
        if not isinstance(candidates, tuple):
            raise TypeError(
                "prompt.candidate.score: 'candidates' port must be a tuple, "
                f"got {type(candidates).__name__}"
            )
        for candidate in candidates:
            if not isinstance(candidate, str):
                raise TypeError(
                    "prompt.candidate.score: 'candidates' entries must be str, "
                    f"got {type(candidate).__name__}"
                )
        state = input.port_values.get("state")
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "prompt.candidate.score: 'state' port must be an AgentState "
                f"instance or None, got {type(state).__name__}"
            )
        scored: tuple[tuple[str, float], ...] = tuple((candidate, 1.0) for candidate in candidates)
        return NodeOutput(port_values={"scored": scored})


@plugin(
    id="phase.concept.template_select.prompt_candidate_score",
    Config=None,
    provides=("concept::prompt.candidate.score",),
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
                "phase_concept_template_select_prompt_candidate_score.checked",
                "phase_concept_template_select_prompt_candidate_score.served",
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
    executor = PromptCandidateScoreExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["PromptCandidateScoreExecutor", "setup"]
