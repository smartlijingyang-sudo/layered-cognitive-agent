"""phase.perceive.fold — terminal-of-typing: collapse manifest → observation.

ADR-0221: takes the raw ``manifest`` from ``phase.perceive.observe`` and
projects it onto the closed ``observation`` port that downstream
``think.main`` consumes. This is the typed cross-phase boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType, ContentType
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class PerceiveFoldExecutor:
    """Terminal-of-typing node: ``manifest`` → ``observation``."""

    semantic_name: str = "phase.perceive.fold"
    region: str = "perceive"
    declared_inputs: tuple[PortName, ...] = ("manifest",)
    declared_outputs: tuple[PortName, ...] = (
        "in_assembled_manifest",
        "observation",
    )

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del context
        manifest = input.port_values.get("manifest")
        # The ``observation`` port feeds phase.reflect.score, whose critic
        # reads ``Observation.success``. Project the manifest into a typed
        # Observation instead of leaking the raw manifest across the boundary.
        observation = Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=manifest,
            content_type=ContentType.TEXT,
        )
        return NodeOutput(
            port_values={
                "in_assembled_manifest": manifest,
                "observation": observation,
                "routing": RoutingDecision(action_type=ActionType.RESPOND),
            },
        )


@plugin(
    id="phase.perceive.fold",
    provides=("perceive::phase.perceive.fold",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/declarative/test_phase_subgraph_parity.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("phase_perceive_fold.checked", "phase_perceive_fold.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: object) -> None:
    del config
    ctx.provide("perceive::phase.perceive.fold", PerceiveFoldExecutor())


__all__ = ["PerceiveFoldExecutor", "setup"]
