"""region:intervene.interrupt — typed HITL pause primitive.

Per ADR-0228 §Decision 4: reads the upstream ``decision`` and
``spine_seq`` ports, emits a typed ``Command(kind="approve"|"reject")``
plus a ``RoutingDecision(should_terminate=True, next_hint="intervene.resume")``.
The kernel sees ``should_terminate`` and pauses, persisting the
``Command`` to the spine (observation). ``intervene.resume`` re-projects
the persisted ``Command`` as a typed port on the next run.

External reference: Hermes-agent ``_interrupt_requested``, LangGraph
``interrupt()`` / ``Command(resume=...)``, AutoGen handoff-to-user
(rejected: string-based, violates typed Contract C13).

Boundary discipline:

- AGENTS.md §3 C4 — Reducer single-write: this node only emits typed
  ports; it never mutates ``AgentState``.
- AGENTS.md §3 C5 — capability monotonicity: ``declared_inputs`` is a
  subset of the upstream grant (``decision``, ``spine_seq``); no new
  effects are declared (cognitive-plane node).
- AGENTS.md §3 C7 — control / observation split: ``Command`` is a
  control-plane artifact, but every emission lands in the journal as a
  ``SessionEvent`` first (observation); this node returns
  ``should_terminate=True`` and lets the kernel persist, it does not
  mutate state directly.
- AGENTS.md §3 C11 — no new spine EP introduced; ``Command`` lands
  via the existing typed-port path.
- AGENTS.md §3 C13 — ``Command`` is the Pydantic-frozen
  ``extra="forbid"`` cross-graph DTO at ``lca.contracts.protocols.graph.command``.

Canonical node shape (ADR-0228 §Decision 2): hand-written
``@dataclass(frozen=True, slots=True)`` + ``@plugin(...)`` carrier.
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
from lca.contracts.models.core.execution.decision import Decision, requires_human_input
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.command import Command
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.context.context import SpineContext

# ``Decision.action_type`` value that opts into the HITL pause path.
# The upstream ``think.decision.parse`` (and the legacy code path) emit
# this literal as the human-handoff intent; everything else resolves to
# a reject-shell command.
_HITL_ACTION_TYPE = "ask_user"

# Provenance actor stamped on the issued ``Command``. v1 only ships the
# user-driven path; policy / system actors land with later items.
_DEFAULT_ISSUED_BY = "user"


def _resolve_port(name: str, *, input: NodeInput, context: NodeContext) -> Any:
    """Read a declared port from ``input.port_values`` or ``context.runtime``."""
    value = input.port_values.get(name)
    if value is None and getattr(context, "runtime", None) is not None:
        value = getattr(context.runtime, name, None)
        if value is None and hasattr(context.runtime, "get"):
            value = context.runtime.get(name)
    if value is None:
        raise TypeError(
            f"intervene.interrupt: '{name}' port must be supplied via input.port_values or context.runtime"
        )
    return value


def _peek_port(name: str, *, input: NodeInput, context: NodeContext) -> Any:
    """Read an optional port; ``None`` when no producer wired it live."""
    value = input.port_values.get(name)
    if value is None and getattr(context, "runtime", None) is not None:
        value = getattr(context.runtime, name, None)
        if value is None and hasattr(context.runtime, "get"):
            value = context.runtime.get(name)
    return value


@dataclass(frozen=True, slots=True)
class InterruptExecutor:
    """intervene node: project a HITL ``Decision`` into a typed ``Command``.

    The node is a pure transform of the ``decision`` + ``spine_seq``
    ports: it never reads runtime state, never mutates ``AgentState``,
    and never touches I/O. The kernel pauses on
    ``RoutingDecision.should_terminate=True`` and persists the typed
    ``Command`` to the spine.
    """

    semantic_name: str = "intervene.interrupt"
    region: str = "intervene"
    declared_inputs: tuple[PortName, ...] = ("decision", "spine_seq")
    declared_outputs: tuple[PortName, ...] = ("command", "routing")

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """intervene 子图节点入口。

        inputs 端口(yaml): decision, spine_seq
        outputs 端口(yaml): command, routing
        """
        decision = _resolve_port("decision", input=input, context=context)
        if not isinstance(decision, Decision):
            raise TypeError(
                f"intervene.interrupt expects Decision on port 'decision', got {type(decision).__name__}"
            )
        seq = _peek_port("spine_seq", input=input, context=context)
        if seq is None:
            # No producer wires ``spine_seq`` live (outer edge carries only
            # the approval routing predicate). Anchor on the live spine tail
            # instead of failing the pause: the kernel persists this Command
            # immediately after, so the tail is the issuance point.
            seq = SpineContext.current_sequence()
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise TypeError(
                f"intervene.interrupt expects int on port 'spine_seq', got {type(seq).__name__}"
            )
        if decision.action_type == _HITL_ACTION_TYPE or requires_human_input(decision.tool_calls):
            kind = "approve"
        else:
            kind = "reject"
        cmd = Command(
            kind=kind,  # type: ignore[arg-type]
            payload={"decision_id": decision.decision_id},
            issued_by=_DEFAULT_ISSUED_BY,
            issued_at_seq=seq,
        )
        routing = RoutingDecision(
            action_type=ActionType.ASK_HUMAN,
            should_terminate=True,
            next_hint="intervene.resume",
        )
        return NodeOutput(port_values={"command": cmd, "routing": routing})


@plugin(
    id="lca.nodes.intervene.interrupt",
    Config=None,
    provides=("intervene::intervene.interrupt",),
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
                "phase_intervene_interrupt.checked",
                "phase_intervene_interrupt.served",
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
    executor = InterruptExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["InterruptExecutor", "setup"]
