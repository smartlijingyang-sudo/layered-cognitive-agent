"""Tests for region:intervene.resume plugin (ADR-0228 §Decision 4).

Verifies the typed ``intervene.resume`` node that converts a persisted
``Command`` (re-projected by the kernel from the spine) into the typed
``Decision`` port the think phase consumes. Five cases pin the
``Command.kind`` → ``Decision.action_type`` mapping, the payload pass-
through, and the deterministic ``decision_id`` derivation.
"""

from __future__ import annotations

import pytest

from lca.contracts.models.cognition.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.command import Command
from lca.nodes.intervene.resume.resume import ResumeExecutor


def _ctx() -> NodeContext:
    """Minimal NodeContext; resume is a pure transform of input ports."""
    return NodeContext(runtime={}, budget={}, metadata={})


def _cmd(
    kind: str,
    *,
    payload: dict | None = None,
    issued_by: str = "user",
    issued_at_seq: int = 42,
) -> Command:
    """Build a Command for the test (Pydantic frozen — kwargs only)."""
    return Command(
        kind=kind,  # type: ignore[arg-type]
        payload=payload,
        issued_by=issued_by,
        issued_at_seq=issued_at_seq,
    )


@pytest.mark.asyncio
async def test_resume_approve_emits_respond_decision() -> None:
    """Command(kind="approve") → Decision(action_type="respond")."""
    executor = ResumeExecutor()
    cmd = _cmd("approve", payload={"text": "ok"})
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"command": cmd}),
    )
    decision: Decision = output.port_values["decision"]
    assert isinstance(decision, Decision)
    assert decision.action_type == "respond"
    assert decision.extra["command_kind"] == "approve"


@pytest.mark.asyncio
async def test_resume_reject_emits_respond_decision_with_rejected_flag() -> None:
    """Command(kind="reject") → Decision(action_type="respond", payload.rejected==True)."""
    executor = ResumeExecutor()
    cmd = _cmd("reject", payload={"reason": "bad"})
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"command": cmd}),
    )
    decision: Decision = output.port_values["decision"]
    assert decision.action_type == "respond"
    assert decision.extra["command_action_payload"] == {"rejected": True}


@pytest.mark.asyncio
async def test_resume_resume_emits_use_tool_decision() -> None:
    """Command(kind="resume") → Decision(action_type="use_tool")."""
    executor = ResumeExecutor()
    cmd = _cmd("resume", payload={"step": 7})
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"command": cmd}),
    )
    decision: Decision = output.port_values["decision"]
    assert decision.action_type == "use_tool"
    assert decision.extra["command_kind"] == "resume"


@pytest.mark.asyncio
async def test_resume_redirect_emits_use_tool_decision_with_payload_passthrough() -> None:
    """Command(kind="redirect") → Decision(action_type="use_tool"), payload 透传."""
    executor = ResumeExecutor()
    payload = {"tool": "search", "args": {"q": "weather"}}
    cmd = _cmd("redirect", payload=payload)
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"command": cmd}),
    )
    decision: Decision = output.port_values["decision"]
    assert decision.action_type == "use_tool"
    assert decision.extra["command_action_payload"] == payload
    assert decision.extra["command_kind"] == "redirect"


@pytest.mark.asyncio
async def test_resume_decision_id_is_resumed_issued_at_seq() -> None:
    """decision_id 形如 ``resumed-{issued_at_seq}``(确定性、可重放)。"""
    executor = ResumeExecutor()
    cmd = _cmd("approve", issued_at_seq=1234)
    output = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"command": cmd}),
    )
    decision: Decision = output.port_values["decision"]
    assert decision.decision_id == "resumed-1234"
    # And the spine provenance survives into the typed bag so the
    # journal → resume chain is auditable from the Decision alone.
    assert decision.extra["command_issued_at_seq"] == 1234
    assert decision.extra["command_issued_by"] == "user"


@pytest.mark.asyncio
async def test_resume_is_pure_across_instances() -> None:
    """Two separately-constructed executors agree on every deterministic field.

    The :class:`Decision` DTO auto-stamps ``created_at`` on construction
    (existing ``utc_now`` default), so we compare the deterministic
    fields rather than full dataclass equality. The point: this node
    carries no instance-level state that leaks into the typed output.
    """
    cmd = _cmd("approve", payload={"x": 1}, issued_at_seq=9)
    inp = NodeInput(port_values={"command": cmd})
    out_a = await ResumeExecutor().node_execute(_ctx(), inp)
    out_b = await ResumeExecutor().node_execute(_ctx(), inp)
    dec_a: Decision = out_a.port_values["decision"]
    dec_b: Decision = out_b.port_values["decision"]
    assert dec_a.decision_id == dec_b.decision_id == "resumed-9"
    assert dec_a.action_type == dec_b.action_type == "respond"
    assert dec_a.rationale == dec_b.rationale
    assert dec_a.extra == dec_b.extra


@pytest.mark.asyncio
async def test_resume_rejects_unknown_kind() -> None:
    """Unknown ``Command.kind`` fails loud at the seam, not silently."""
    # Pydantic forbids unknown kinds at construction, so build a
    # payload-only Command and monkey-patch ``kind`` to simulate the
    # invariant violation at the producer.
    cmd = _cmd("approve")
    object.__setattr__(cmd, "kind", "bogus")  # bypass frozen for the test
    executor = ResumeExecutor()
    with pytest.raises(ValueError, match=r"unknown Command\.kind"):
        await executor.node_execute(
            _ctx(),
            NodeInput(port_values={"command": cmd}),
        )


@pytest.mark.asyncio
async def test_resume_rejects_missing_command_port() -> None:
    """Missing required ``command`` port raises ValueError at the seam."""
    executor = ResumeExecutor()
    with pytest.raises(ValueError, match="requires port 'command'"):
        await executor.node_execute(
            _ctx(),
            NodeInput(port_values={}),
        )
