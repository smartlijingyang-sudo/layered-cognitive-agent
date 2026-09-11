"""phase.concept.perceive_turn.perceive_observation_fold — typed fold.

``concept.perceive.turn`` 内嵌节点 3:typed ``tuple[Observation, ...]``
→ ``tuple[ContextItem, ...]`` — 把多个 typed Observation 折成
typed ``ContextItem`` 列表, 准备 manifest compose。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.perceive.perception import ContextItem
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
class PerceiveObservationFoldExecutor:
    """``concept.perceive.turn`` 节点 3:observations → context_items。"""

    semantic_name: str = "perceive.observation.fold"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("observations",)
    declared_outputs: tuple[PortName, ...] = ("context_items",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """perceive.observation.fold 入口。

        inputs 端口(yaml):observations (tuple[Observation, ...])
        outputs 端口(yaml):context_items (tuple[ContextItem, ...])
        """
        del context
        observations = input.port_values.get("observations") or ()
        if not isinstance(observations, tuple):
            raise TypeError(
                "perceive.observation.fold: 'observations' port must be a "
                f"tuple, got {type(observations).__name__}"
            )
        items: list[ContextItem] = []
        for obs in observations:
            if not isinstance(obs, Observation):
                raise TypeError(
                    "perceive.observation.fold: observations entries must be "
                    f"Observation instances, got {type(obs).__name__}"
                )
            items.append(_fold(obs))
        return NodeOutput(port_values={"context_items": tuple(items)})


def _fold(observation: Observation) -> ContextItem:
    """Project one Observation onto a typed ContextItem for the manifest.

    ItemKind is a closed Literal — for P8 we map raw text inputs to
    "memory" and structured payloads to "data"-equivalent
    ("workspace_artifacts"). The PerceiveHub provider will tighten
    this mapping when it lands; this projector stays a typed boundary.
    """
    payload: Any = observation.payload
    kind = "memory" if isinstance(payload, str) else "workspace_artifacts"
    return ContextItem(
        kind=kind,
        payload=payload,
        provenance=observation.tool_call_id or "",
        extra=dict(observation.extra or {}),
    )


@plugin(
    id="phase.concept.perceive_turn.perceive_observation_fold",
    Config=None,
    provides=("concept::perceive.observation.fold",),
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
                "phase_concept_perceive_turn_perceive_observation_fold.checked",
                "phase_concept_perceive_turn_perceive_observation_fold.served",
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
    executor = PerceiveObservationFoldExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["PerceiveObservationFoldExecutor", "_fold", "setup"]
