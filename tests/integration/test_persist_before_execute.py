"""Spec §C: persist-before-execute in ``Body.dispatch_tool_call``.

The assistant ``tool_calls`` row must land in the journal BEFORE the tool
runs. If ``Session.append`` fails between the assistant-message write and
tool execution, the tool never runs and the turn breaks with an
``EffectReceipt(outcome=FAILED, error_code="session_persistence_failed")``.

This is the root-cause fix for the original ``run_cc39610072bf`` bug:
the orphan cycle cannot start because the assistant row is in the journal
before the next LLM call sees the history.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.cognition.body.executor.simple_body import SimpleBody
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.models.core.execution.result import ToolExecutionError
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.models.team.role.team import CacheConfig, RetryPolicy
from lca.contracts.protocols.runtime.infra.infra import Tool
from lca.runtime.session.run_session_writer import RunSessionWriter

# ── Minimal in-memory SessionProtocol fixture ──────────────────────────────


@dataclass
class _StoredEvent:
    type: str
    seq: int
    time: float
    data: dict[str, Any]
    surface_op: Any | None
    source_event_seqs: tuple[int, ...] | None


@dataclass
class _FlakySession:
    """``SessionProtocol`` shaped fixture that fails ``append`` after N calls.

    ``fail_after`` counts how many ``append`` calls succeed before the next
    call raises ``RuntimeError("session.append failed")``. Mirrors the
    hermes-agent test pattern for partial-write failures.
    """

    events: list[_StoredEvent] = field(default_factory=list)
    next_seq: int = 0
    fail_after: int = 0

    def append(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        surface_op: Any | None = None,
        source_event_seqs: tuple[int, ...] | None = None,
    ) -> _StoredEvent:
        if self.fail_after == 0:
            raise RuntimeError("session.append failed")
        self.fail_after -= 1
        event = _StoredEvent(
            type=event_type,
            seq=self.next_seq,
            time=self.next_seq * 1000.0,
            data=dict(data),
            surface_op=surface_op,
            source_event_seqs=source_event_seqs,
        )
        self.next_seq += 1
        self.events.append(event)
        return event

    def snapshot_events(self) -> tuple[_StoredEvent, ...]:
        return tuple(self.events)

    def request_header(self) -> Any | None:
        return None

    @property
    def id(self) -> str:
        return "test-session"


# ── Minimal Tool / SafeExecutor / ToolRegistry fakes ────────────────────────


@dataclass
class _Recorder:
    """Track whether the tool body ever ran."""

    calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _FakeTool:
    """Tool whose ``execute`` records the call and returns a success Observation."""

    name: str
    recorder: _Recorder
    effect_kind: str = "ephemeral"
    is_idempotent: bool = True

    async def execute(self, args: dict[str, Any]) -> Any:
        from lca.contracts.atoms.ids.ids import new_id
        from lca.contracts.models.core.execution.decision import Observation

        self.recorder.calls.append({"name": self.name, "args": dict(args)})
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"echo": args},
        )


@dataclass
class _FakeToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)


@dataclass
class _FakeSafeExecutor:
    """SafeExecutor stub that delegates to ``tool.execute`` directly.

    Skips permission/caching/retry — the persist-before-execute invariant
    lives at the Body layer, not in the executor.
    """

    async def execute(
        self,
        tool: Tool,
        args: dict[str, Any],
        retry_policy: RetryPolicy,
        cache_config: CacheConfig,
        invocation_id: str = "",
    ) -> Any:
        del retry_policy, cache_config
        return await tool.execute(args)


def _state() -> AgentState:
    from lca.contracts.models.core.policy.budget import create_budget

    return AgentState(
        trace_id="trace-1",
        step=0,
        turn=0,
        budget=create_budget(max_steps=10),
        history=[],
    )


def _decision_with_one_tool_call(call_id: str = "call-1", tool_name: str = "echo") -> Decision:
    return Decision(
        decision_id="dec-1",
        action_type=ActionType.USE_TOOL.value,
        rationale="test",
        confidence=1.0,
        tool_calls=[ToolCall(call_id=call_id, tool_name=tool_name, arguments={"x": 1})],
    )


# ── Persist-before-execute tests ────────────────────────────────────────────


def test_assistant_message_in_journal_before_tool_execution() -> None:
    """If ``Session.append`` fails on the assistant-message write,
    the tool never runs and the receipt reports session_persistence_failed."""
    session = _FlakySession(fail_after=0)  # every append fails
    writer = RunSessionWriter(session=session)
    recorder = _Recorder()
    tool = _FakeTool(name="echo", recorder=recorder)
    registry = _FakeToolRegistry(tools={"echo": tool})

    body = SimpleBody(
        tool_registry=registry,  # type: ignore[arg-type]
        safe_executor=_FakeSafeExecutor(),  # type: ignore[arg-type]
        transport_registry=None,  # type: ignore[arg-type]
        action_registry=None,  # type: ignore[arg-type]
        writer=writer,
    )

    receipt = asyncio.run(body.dispatch_tool_call(decision=_decision_with_one_tool_call()))

    # Receipt is rejected: persistence failed before tool execution, tool never ran.
    assert isinstance(receipt, EffectReceipt)
    assert receipt.outcome is EffectOutcome.FAILED
    assert receipt.error_code == "session_persistence_failed"
    # Tool never executed.
    assert recorder.calls == []


def test_tool_result_persisted_after_tool_execution() -> None:
    """After successful tool execution the journal holds:
    [user_message, assistant_message, tool_result] in that order.
    """
    session = _FlakySession(fail_after=10**6)  # never fail
    writer = RunSessionWriter(session=session)
    # Pre-populate the user message so the wire shape has user → assistant → tool.
    writer.append_user_message(message_id="u1", role="user", content="hi")
    recorder = _Recorder()
    tool = _FakeTool(name="echo", recorder=recorder)
    registry = _FakeToolRegistry(tools={"echo": tool})

    body = SimpleBody(
        tool_registry=registry,  # type: ignore[arg-type]
        safe_executor=_FakeSafeExecutor(),  # type: ignore[arg-type]
        transport_registry=None,  # type: ignore[arg-type]
        action_registry=None,  # type: ignore[arg-type]
        writer=writer,
    )

    receipt = asyncio.run(body.dispatch_tool_call(decision=_decision_with_one_tool_call()))

    assert isinstance(receipt, EffectReceipt)
    assert receipt.outcome is EffectOutcome.SUCCEEDED
    assert recorder.calls == [{"name": "echo", "args": {"x": 1}}]

    surface_events = [e for e in session.events if e.type.startswith("surface/")]
    assert [e.type for e in surface_events] == [
        "surface/user_message",
        "surface/assistant_message",
        "surface/tool_result",
    ]


def test_dispatch_tool_call_without_writer_raises() -> None:
    """``Body.dispatch_tool_call`` requires a bound RunSessionWriter.

    Per ADR-0226 §1: writer methods fail loud. No silent None; the
    persist-before-execute path must not run if the writer is unbound.
    """
    recorder = _Recorder()
    tool = _FakeTool(name="echo", recorder=recorder)
    registry = _FakeToolRegistry(tools={"echo": tool})

    body = SimpleBody(
        tool_registry=registry,  # type: ignore[arg-type]
        safe_executor=_FakeSafeExecutor(),  # type: ignore[arg-type]
        transport_registry=None,  # type: ignore[arg-type]
        action_registry=None,  # type: ignore[arg-type]
        writer=None,  # type: ignore[arg-type]
    )

    with pytest.raises(ToolExecutionError):
        asyncio.run(body.dispatch_tool_call(decision=_decision_with_one_tool_call()))
    assert recorder.calls == []
