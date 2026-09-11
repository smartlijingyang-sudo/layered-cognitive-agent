"""phase.concept.perceive_turn.perceive_sensor_run — typed sensor runner.

``concept.perceive.turn`` 内嵌节点 2:typed ``tuple[Any, ...]`` → tuple
(``Observation``, ...) — sensor 层把 run inputs 转成 typed ``Observation``。

P8 阶段把 sensor 节点作为 passthrough 占位,真正的 PerceiveHub 接入
留待后续 PR(perceive sensor 是感知能力 seam,不归 cognition 层)。
typed output 沿 ADR §4.2 boundary contract: ``Observation`` 是
``Observation`` typed DTO,不发明新字段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class PerceiveSensorRunExecutor:
    """``concept.perceive.turn`` 节点 2:raw_inputs → tuple[Observation, ...]。"""

    semantic_name: str = "perceive.sensor.run"
    region: str = "concept"
    declared_inputs: tuple[PortName, ...] = ("raw_inputs",)
    declared_outputs: tuple[PortName, ...] = ("observations",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """perceive.sensor.run 入口。

        inputs 端口(yaml):raw_inputs (tuple[Any, ...])
        outputs 端口(yaml):observations (tuple[Observation, ...])
        """
        del context
        raw_inputs = input.port_values.get("raw_inputs") or ()
        if not isinstance(raw_inputs, tuple):
            raise TypeError(
                "perceive.sensor.run: 'raw_inputs' port must be a tuple, "
                f"got {type(raw_inputs).__name__}"
            )
        observations: list[Observation] = []
        for idx, raw in enumerate(raw_inputs):
            obs = _project(raw, idx)
            observations.append(obs)
        return NodeOutput(port_values={"observations": tuple(observations)})


def _project(raw: Any, idx: int) -> Observation:
    """Project one run_input element onto a typed ``Observation``.

    Sensor 层的实际感知逻辑(读 inbox、读 memory、读 file store 等)留
    待 PerceiveHub provider 接入。本节点只把已经到达的数据转成 typed
    ``Observation``, 让下游 fold 节点拿到 typed 集合。
    """
    payload = raw if not isinstance(raw, Exception) else None
    error = repr(raw) if isinstance(raw, Exception) else None
    return Observation(
        observation_id=f"obs_{idx}_{new_id('sensor')}",
        success=error is None,
        payload=payload,
        tool_call_id=None,
        error=error,
    )


@plugin(
    id="phase.concept.perceive_turn.perceive_sensor_run",
    Config=None,
    provides=("concept::perceive.sensor.run",),
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
                "phase_concept_perceive_turn_perceive_sensor_run.checked",
                "phase_concept_perceive_turn_perceive_sensor_run.served",
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
    executor = PerceiveSensorRunExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["PerceiveSensorRunExecutor", "_project", "setup"]
