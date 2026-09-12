"""phase.reflect.admit_recovery — recovery-routing hint node.

ADR-0221: terminal-of-typing for the reflect subgraph. Reads the
``reflection`` payload from the upstream score node and emits an
``admit_recovery`` port + a ``next_hint`` hint so the outer interpreter's
loop guard can route to recovery edges when the observation indicates
failure.

This node mirrors the previous ``RecoveryReflectExecutor`` semantics:
the verdict is purely about routing — it does not modify the typed
``reflection`` payload.
"""

from __future__ import annotations

from collections.abc import Mapping
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


def _is_failure(observation: object) -> bool:
    if observation is None:
        return True
    if isinstance(observation, Mapping):
        success = observation.get("success")
        return success is False or success is None
    return bool(getattr(observation, "success", None) is False)


@dataclass(frozen=True, slots=True)
class ReflectAdmitRecoveryExecutor:
    """Decide whether the outer loop may route through recovery edges."""

    semantic_name: str = "phase.reflect.admit_recovery"
    region: str = "phase:reflect"
    declared_inputs: tuple[PortName, ...] = ("observation", "reflection")
    # First-principle dead-port removal (C13 信息血统闭合):
    # ``admit_recovery`` was previously listed as a port but had no
    # ``PortName`` registration and no ``port_values`` consumer in the
    # kernel — the recovery edge reads ``result.next_hints.admit_recovery``
    # (not port_values), so the port was untyped, unregistered, and
    # unreferenced. The plugin emits the recovery hint via
    # ``next_hint`` only; downstream routing reads ``next_hints`` through
    # the kernel's edge DSL. Removing the port stops ``NodeOutput``
    # from rejecting the unknown key.
    declared_outputs: tuple[PortName, ...] = ("reflection",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        del context
        observation = input.port_values.get("observation")
        admit = _is_failure(observation)
        return NodeOutput(
            port_values={
                "reflection": input.port_values.get("reflection"),
            },
            next_hint="admit_recovery" if admit else None,
        )


@plugin(
    id="phase.reflect.admit_recovery",
    provides=("phase:reflect::phase.reflect.admit_recovery",),
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
            descriptors=("phase_reflect_admit_recovery.checked", "phase_reflect_admit_recovery.served")
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
    ctx.provide("phase:reflect::phase.reflect.admit_recovery", ReflectAdmitRecoveryExecutor())


__all__ = ["ReflectAdmitRecoveryExecutor", "_is_failure", "setup"]
