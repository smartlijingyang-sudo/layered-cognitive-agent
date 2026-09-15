"""phase.concept.template_select.prompt_candidate_pick — typed TemplateSelection composer.

concept.template.select 图节点 3:typed ``tuple[tuple[str, float], ...]`` + state
→ ``TemplateSelection`` frozen boundary DTO(ADR-0220 §4.1)。

P3 骨架:取 ``scored[0][0]`` 作 template_id,``variant="react"``,
``decision_path="profile_default"``。真实 selector 决策在 P4/P5 由
``PromptTemplateSelector`` provider 接管。
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
from lca.contracts.models.cognition.boundary import TemplateSelection
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
class PromptCandidatePickExecutor:
    """concept.template.select 节点 3:scored → TemplateSelection."""

    semantic_name: str = "prompt.candidate.pick"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("scored", "state")
    declared_outputs: tuple[PortName, ...] = ("template_selection",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """prompt.candidate.pick 入口。

        inputs 端口(yaml):scored (tuple[tuple[str, float], ...]), state (AgentState)
        outputs 端口(yaml):template_selection (TemplateSelection)
        """
        del context
        scored = input.port_values.get("scored")
        if scored is None:
            scored = ()
        if not isinstance(scored, tuple):
            raise TypeError(
                f"prompt.candidate.pick: 'scored' port must be a tuple, got {type(scored).__name__}"
            )
        state = input.port_values.get("state")
        if state is not None and not isinstance(state, AgentState):
            raise TypeError(
                "prompt.candidate.pick: 'state' port must be an AgentState "
                f"instance or None, got {type(state).__name__}"
            )
        if not scored:
            selection = TemplateSelection(
                template_id="react_prompt",
                variant="react",
                decision_path="profile_default",
            )
        else:
            first = scored[0]
            if not isinstance(first, tuple) or len(first) != 2 or not isinstance(first[0], str):
                raise TypeError(
                    "prompt.candidate.pick: 'scored' entries must be (str, float) tuples"
                )
            selection = TemplateSelection(
                template_id=first[0],
                variant="react",
                decision_path="profile_default",
            )
        return NodeOutput(port_values={"template_selection": selection})


@plugin(
    id="phase.concept.template_select.prompt_candidate_pick",
    Config=None,
    provides=("concept::prompt.candidate.pick",),
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
                "phase_concept_template_select_prompt_candidate_pick.checked",
                "phase_concept_template_select_prompt_candidate_pick.served",
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
    executor = PromptCandidatePickExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["PromptCandidatePickExecutor", "setup"]
