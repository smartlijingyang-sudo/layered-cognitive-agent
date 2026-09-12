"""control.remember.admit — NodeExecutor control node for the remember.admit slot."""

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
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.gate.control_verdict import ControlVerdict, ControlVerdictKind
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class RememberAdmitExecutor:
    """Control node: admit / deny based on observation + reflection + status."""

    semantic_name: str = "control.remember.admit"
    region: str = "phase:remember"
    declared_inputs: tuple[PortName, ...] = ("observation", "reflection")
    declared_outputs: tuple[PortName, ...] = ("verdict",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        observation = input.port_values.get("observation")
        reflection = input.port_values.get("reflection")
        runtime = context.runtime or {}
        state = runtime.get("agent_state")
        status = getattr(state, "status", TaskStatus.WORKING) if state is not None else TaskStatus.WORKING
        if not isinstance(observation, Observation) or not isinstance(reflection, Reflection):
            verdict = ControlVerdict(
                kind=ControlVerdictKind.DENY,
                detail="memory admission requires outcome and reflection",
                plugin_id="control.executor.remember-admit",
            )
            hint = "stop"
        elif status != TaskStatus.WORKING:
            verdict = ControlVerdict(
                kind=ControlVerdictKind.DENY,
                detail="terminal run does not admit new memory",
                plugin_id="control.executor.remember-admit",
            )
            hint = "stop"
        else:
            verdict = ControlVerdict(
                kind=ControlVerdictKind.ALLOW,
                detail="turn is admissible to memory",
                plugin_id="control.executor.remember-admit",
            )
            hint = None
        return NodeOutput(port_values={"verdict": verdict}, next_hint=hint)


@plugin(
    id="control.remember.admit",
    provides=("phase:remember::control.remember.admit",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    test_suite="tests/declarative/test_control_contributions.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            control_slots=(ControlSlot.REMEMBER_ADMIT,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("memory.write",)),
        observability=EvidenceContract(
            descriptors=("control_remember_admit.checked", "control_remember_admit.served")
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
    ctx.provide("phase:remember::control.remember.admit", RememberAdmitExecutor())


__all__ = ["RememberAdmitExecutor", "setup"]
