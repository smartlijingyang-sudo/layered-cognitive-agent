"""phase.intervene.resume — re-feed persisted Command to think phase.

Per ADR-0228 §Decision 4: the kernel reads a persisted ``Command`` from
the spine (observation), re-projects it as a typed port via this node,
and forwards it as a typed ``Decision`` input to the ``think`` phase.
This replaces the implicit ``ask_user`` path that previously piggy-
backed on ``Decision.action_type``.

Boundary discipline:

- AGENTS.md §3 C4 — the node does not mutate ``AgentState``; it only
  emits a typed ``Decision`` port.
- AGENTS.md §3 C7 — the node is a control-plane re-entry: it consumes
  a control-plane ``Command`` (already journal-first) and emits a typed
  ``Decision`` port. The journal projection is the source of truth;
  this node is a pure transform.
- AGENTS.md §3 C11 — no new spine EP is introduced; ``Command`` lands
  as a typed port, not a new event.
- AGENTS.md §3 C13 — ``Decision`` is the existing frozen cross-graph
  DTO (ADR-0220 §4.2); the command payload and provenance ride in the
  ``extra`` typed bag instead of inventing new fields.

Canonical node shape (ADR-0228 §Decision 2): hand-written
``@dataclass(frozen=True, slots=True)`` + ``@plugin(...)`` carrier, no
decorator magic.
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
from lca.contracts.models.cognition.decision import Decision
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_COMMAND_TO_ACTION_TYPE: dict[str, str] = {
    "approve": "respond",
    "reject": "respond",
    "resume": "use_tool",
    "redirect": "use_tool",
}

_REJECTED_PAYLOAD: dict[str, Any] = {"rejected": True}


def _action_type_for(kind: str) -> str:
    """Map a Command.kind to the Decision.action_type the think phase sees.

    ``approve`` / ``reject`` → ``respond`` (the agent acknowledges the
    user); ``resume`` / ``redirect`` → ``use_tool`` (the agent continues
    execution with the payload as a tool call).
    """
    try:
        return _COMMAND_TO_ACTION_TYPE[kind]
    except KeyError as exc:
        raise ValueError(f"unknown Command.kind: {kind!r}") from exc


def _payload_for(kind: str, cmd_payload: dict[str, Any] | None) -> dict[str, Any]:
    """Project a ``Command`` payload into the ``Decision`` action payload.

    ``reject`` stamps a ``{"rejected": True}`` marker; other kinds pass
    the payload through unchanged. ``None`` becomes an empty dict so the
    downstream port value is always a non-optional mapping.
    """
    if kind == "reject":
        return dict(_REJECTED_PAYLOAD)
    return dict(cmd_payload or {})


@dataclass(frozen=True, slots=True)
class ResumeExecutor:
    """intervene node: re-derive a typed ``Decision`` from a persisted ``Command``.

    The node is a pure transform: it never reads runtime state, never
    mutates ``AgentState``, and never touches I/O. The kernel re-projects
    the journal-persisted ``Command`` into the ``command`` port; this
    node shapes it into the ``Decision`` the ``think`` phase already
    understands.
    """

    semantic_name: str = "intervene.resume"
    region: str = "region:intervene"
    declared_inputs: tuple[PortName, ...] = ("command",)
    declared_outputs: tuple[PortName, ...] = ("decision",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """intervene 子图节点入口。

        inputs 端口(yaml): command
        outputs 端口(yaml): decision
        """
        del context  # unused: pure function of input ports
        cmd = input.port_values.get("command")
        if cmd is None:
            # Missing required port — fail loud at the seam. The kernel
            # must re-project the persisted Command before this node runs.
            raise ValueError("intervene.resume requires port 'command' (Command); got None")
        if not isinstance(cmd, Command):
            # Fail loud at the seam: the kernel re-projects spine facts
            # as Command, anything else is a producer-side contract bug.
            raise TypeError(
                f"intervene.resume expects Command on port 'command', got {type(cmd).__name__}"
            )
        action_type = _action_type_for(cmd.kind)
        action_payload = _payload_for(cmd.kind, cmd.payload)
        # Provenance rides in the typed ``extra`` bag (ADR-0220 §4.2) so
        # no new fields are invented on the existing ``Decision`` DTO.
        extra: dict[str, Any] = {
            "command_kind": cmd.kind,
            "command_issued_by": cmd.issued_by,
            "command_issued_at_seq": cmd.issued_at_seq,
            "command_action_payload": action_payload,
        }
        decision = Decision(
            decision_id=f"resumed-{cmd.issued_at_seq}",
            action_type=action_type,
            rationale=f"intervene.resume: Command(kind={cmd.kind!r}) re-fed from journal",
            confidence=1.0,
            extra=extra,
        )
        return NodeOutput(port_values={"decision": decision})


@plugin(
    id="lca.nodes.intervene.resume",
    Config=None,
    provides=("region:intervene::intervene.resume",),
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
                "phase_intervene_resume.checked",
                "phase_intervene_resume.served",
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
    executor = ResumeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ResumeExecutor", "setup"]
