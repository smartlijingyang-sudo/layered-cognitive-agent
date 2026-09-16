"""phase.concept.act_subgraph.act_fanout — typed envelope fan-out boundary.

``concept.act_subgraph`` 内嵌节点:``envelopes`` (tuple) →
``envelopes`` (preserved) + ``RoutingDecision``.

PR-3 (G-18, ADR-0232): N:N fanout. The node now reads either:

- ``envelopes`` typed port (``tuple[CommandEnvelope, ...]``) — N:N path,
  emits ``fanout_ntom`` when ``len(envelopes) >= 2``,
  ``fanout_1to1`` when ``len == 1``, ``fanout_empty`` when 0; or
- ``envelope`` typed port (``CommandEnvelope | None``) — 1:1 back-compat
  path, same routing decision as before.

Both ports coexist on the typed-port graph; PR-3 wires
``act.envelope → act.fanout`` via the new ``envelopes`` port while
keeping the single-value ``envelope`` port for any consumer that has
not yet been upgraded.  ``declared_inputs`` therefore exposes both
ports.

``declared_outputs`` keeps ``envelope`` as the 1:1 pass-through so
``act.dispatch`` can still consume a single envelope; ``envelopes``
is the N:N surface for future dispatch upgrades.

ADR-0219 §5.5 typed-port contract: ``declared_inputs`` /
``declared_outputs`` are compile-time closed sets; this node reads
``envelopes`` (preferred) or ``envelope`` (back-compat) and writes
``envelopes`` / ``envelope`` / ``routing``.  It does not touch Body /
Registry / SafeExecutor — execution narrow door (AGENTS.md §3 C10) is
held by ``effect.execute → Body → SafeExecutor → Sandbox``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
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
from lca.contracts.protocols.act.command.envelope import CommandEnvelope
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

# next_hint closed set (ADR-0232 §Decision 1).  Routing layer only;
# never enters ``EXECUTION_POINTS`` (C11 closed set).
NEXT_HINT_FANOUT_NTOM = "fanout_ntom"
NEXT_HINT_FANOUT_1TO1 = "fanout_1to1"
NEXT_HINT_FANOUT_EMPTY = "fanout_empty"


@dataclass(frozen=True, slots=True)
class ActFanoutExecutor:
    """``concept.act.fanout`` 节点:N:N envelope fan-out (typed boundary)。

    Accepts either an ``envelopes`` tuple (preferred, PR-3) or a single
    ``envelope`` (1:1 back-compat).  Emits the same three port values
    on the way out: ``envelopes`` (always a list, possibly empty),
    ``envelope`` (the first envelope or ``None``), and ``routing``
    (RoutingDecision with ``next_hint`` ∈ {fanout_ntom, fanout_1to1,
    fanout_empty}).

    No side effects: no Body / Registry / SafeExecutor calls; no
    envelope construction; no capability / budget / time reads.
    """

    semantic_name: str = "act.fanout"
    region: str = "act"
    declared_inputs: tuple[PortName, ...] = ("envelopes", "envelope")
    declared_outputs: tuple[PortName, ...] = ("envelopes", "envelope", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """act.fanout 入口。

        inputs 端口(yaml): envelopes (tuple[CommandEnvelope, ...] | None, preferred)
                            envelope (CommandEnvelope | None, back-compat)
        outputs 端口(yaml): envelopes (list[CommandEnvelope]), envelope (CommandEnvelope | None),
                            routing (RoutingDecision)
        """
        del context  # unused: pure function of input port value
        port_values: dict[str, Any] = input.port_values

        # Resolve source: prefer the N:N ``envelopes`` typed port; fall back to 1:1 ``envelope``.
        envelopes_in: tuple[CommandEnvelope, ...] | None = port_values.get("envelopes")
        if envelopes_in is not None:
            if not isinstance(envelopes_in, tuple):
                # Accept list-shaped values from upstream typed-port adapters.
                if isinstance(envelopes_in, list):
                    envelopes_in = tuple(envelopes_in)
                else:
                    raise TypeError(
                        "act.fanout: 'envelopes' port must be a tuple/list of "
                        f"CommandEnvelope or None, got {type(envelopes_in).__name__}"
                    )
            for idx, candidate in enumerate(envelopes_in):
                if not isinstance(candidate, CommandEnvelope):
                    raise TypeError(
                        "act.fanout: 'envelopes' port entry "
                        f"#{idx} must be a CommandEnvelope, "
                        f"got {type(candidate).__name__}"
                    )
            envelopes_out: list[CommandEnvelope] = list(envelopes_in)
            envelope_out: CommandEnvelope | None = (
                envelopes_in[0] if envelopes_in else None
            )
            if len(envelopes_in) >= 2:
                next_hint = NEXT_HINT_FANOUT_NTOM
            elif len(envelopes_in) == 1:
                next_hint = NEXT_HINT_FANOUT_1TO1
            else:
                next_hint = NEXT_HINT_FANOUT_EMPTY
        else:
            # Back-compat: 1:1 single-envelope path.
            envelope = port_values.get("envelope")
            if envelope is not None and not isinstance(envelope, CommandEnvelope):
                raise TypeError(
                    "act.fanout: 'envelope' port must be a CommandEnvelope "
                    f"instance or None, got {type(envelope).__name__}"
                )
            envelopes_out = [envelope] if envelope is not None else []
            envelope_out = envelope
            next_hint = (
                NEXT_HINT_FANOUT_1TO1
                if envelope is not None
                else NEXT_HINT_FANOUT_EMPTY
            )

        routing = RoutingDecision(
            action_type=ActionType.USE_TOOL,
            next_node="act.dispatch",
            next_hint=next_hint,
        )
        return NodeOutput(
            port_values={
                "envelopes": envelopes_out,
                "envelope": envelope_out,
                "routing": routing,
            }
        )


@plugin(
    id="phase.concept.act_subgraph.act_fanout",
    Config=None,
    provides=("act::act.fanout",),
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
                "phase_concept_act_subgraph_act_fanout.checked",
                "phase_concept_act_subgraph_act_fanout.served",
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
    executor = ActFanoutExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ActFanoutExecutor", "setup"]
