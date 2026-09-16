"""ADR-0235 / PR-5 (G-9): act.approve.gate reads typed ports only.

The previous ``_resolve_port(context, name)`` helper used
``getattr(context.runtime, name, None)`` to peek at the graph runtime.
That was a ``getattr(..., None)`` silent-skip on the graph / act
boundary and violated the 「act 业务不知道图存在」boundary. PR-5
deletes the helper; the gate reads declared typed ports only.

This module pins:

- A sentinel ``RaisingRuntime`` placed in ``context.runtime`` does
  not raise when the gate executes — the gate never touches it.
- The gate's behavior is unchanged from the prior PR-3.8.6 spec
  (interrupt / skipped / approved / rejected), driven entirely by
  ``Decision.needs_approval`` (typed) and ``Command.kind`` (typed).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.command import Command
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.nodes.intervene.approve_gate import ApproveGateExecutor


@dataclass
class RaisingRuntime:
    """Sentinel that fails loud on any attribute access.

    Used as ``context.runtime`` to prove the gate never reaches into
    graph runtime.
    """

    def __getattr__(self, name: str) -> object:
        raise AssertionError(
            f"act.approve.gate must not reach into context.runtime.{name} "
            f"(ADR-0235 / PR-5 「act 业务不知道图存在」boundary)"
        )


def _ctx() -> NodeContext:
    return NodeContext(runtime=RaisingRuntime(), budget={}, metadata={})


def _decision(*, needs_approval: bool = False) -> Decision:
    return Decision(
        decision_id="dec-1",
        action_type="use_tool",
        rationale="r",
        confidence=1.0,
        needs_approval=needs_approval,
    )


def _cmd(kind: str) -> Command:
    return Command(kind=kind, payload=None, issued_by="user", issued_at_seq=7)


@pytest.mark.asyncio
async def test_approve_gate_does_not_touch_context_runtime() -> None:
    """The gate never reads ``context.runtime.*`` — typed ports only."""
    executor = ApproveGateExecutor()

    # Case 1: needs_approval=True + no command → interrupt path.
    out = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(needs_approval=True),
                "command": None,
            }
        ),
    )
    routing: RoutingDecision = out.port_values["approval_routing"]
    assert routing.next_node == "intervene.interrupt"
    assert routing.next_hint == "approve_interrupt"


@pytest.mark.asyncio
async def test_approve_gate_skipped_path_uses_typed_needs_approval() -> None:
    """``needs_approval=False`` → ``approve_skipped`` to ``act.envelope``.

    Reading is purely from ``Decision.needs_approval`` (typed); the
    runtime is never touched.
    """
    executor = ApproveGateExecutor()
    out = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(needs_approval=False),
                "command": _cmd("approve"),
            }
        ),
    )
    routing = out.port_values["approval_routing"]
    assert routing.next_node == "act.envelope"
    assert routing.next_hint == "approve_skipped"


@pytest.mark.asyncio
async def test_approve_gate_approve_path_uses_typed_command() -> None:
    """``command.kind == "approve"`` → ``approve_approved`` to ``act.envelope``."""
    executor = ApproveGateExecutor()
    out = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(needs_approval=True),
                "command": _cmd("approve"),
            }
        ),
    )
    routing = out.port_values["approval_routing"]
    assert routing.next_node == "act.envelope"
    assert routing.next_hint == "approve_approved"


@pytest.mark.asyncio
async def test_approve_gate_rejected_path() -> None:
    """``command.kind == "reject"`` → ``approve_rejected`` to ``terminal.commit``."""
    executor = ApproveGateExecutor()
    out = await executor.node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "decision": _decision(needs_approval=True),
                "command": _cmd("reject"),
            }
        ),
    )
    routing = out.port_values["approval_routing"]
    assert routing.next_node == "terminal.commit"
    assert routing.next_hint == "approve_rejected"
