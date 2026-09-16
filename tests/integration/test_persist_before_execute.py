"""Spec §C: persist-before-execute in ``Body.dispatch_tool_calls``.

The assistant ``tool_calls`` row must land in the journal BEFORE the tool
runs. If ``Session.append`` fails between the assistant-message write and
tool execution, the tool never runs and the turn breaks with an
``EffectReceipt(outcome=FAILED, error_code="session_persistence_failed")``.

This is the root-cause fix for the original ``run_cc39610072bf`` bug:
the orphan cycle cannot start because the assistant row is in the journal
before the next LLM call sees the history.

PR-2 (G-16): ``dispatch_tool_call`` was renamed to ``dispatch_tool_calls``
(commit-batch over ``decision.tool_calls``). The persist-before-execute
invariant is preserved — exactly ONE ``surface/assistant_message`` row
carrying ALL N declared tool_calls lands BEFORE any tool runs.
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


def _state(step: int = 0, turn: int = 0) -> AgentState:
    """Build an AgentState with ``current_turn`` stored in ``state.extra``.

    ``AgentState`` does not have a top-level ``turn`` attribute; the
    per-call turn lives at ``state.extra["current_turn"]`` (set by the
    ``turn.started.v1`` projection in ``harness.projection.agent_state``).
    ``history`` is a ``@property`` alias over ``control_turns`` and is not
    a constructor kwarg — pass nothing.
    """
    from lca.contracts.models.core.policy.budget import create_budget

    state = AgentState(
        trace_id="trace-1",
        task="test",
        budget=create_budget(max_steps=10),
    )
    state.step = step
    state.extra["current_turn"] = turn
    return state


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

    receipts = asyncio.run(body.dispatch_tool_calls(decision=_decision_with_one_tool_call()))

    # Receipt is rejected: persistence failed before tool execution, tool never ran.
    assert isinstance(receipts, list)
    assert len(receipts) == 1
    receipt = receipts[0]
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

    receipts = asyncio.run(body.dispatch_tool_calls(decision=_decision_with_one_tool_call()))

    assert isinstance(receipts, list)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert isinstance(receipt, EffectReceipt)
    assert receipt.outcome is EffectOutcome.SUCCEEDED
    assert recorder.calls == [{"name": "echo", "args": {"x": 1}}]

    surface_events = [e for e in session.events if e.type.startswith("surface/")]
    assert [e.type for e in surface_events] == [
        "surface/user_message",
        "surface/assistant_message",
        "surface/tool_result",
    ]


def test_dispatch_tool_calls_without_writer_raises() -> None:
    """``Body.dispatch_tool_calls`` requires a bound RunSessionWriter.

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
        asyncio.run(body.dispatch_tool_calls(decision=_decision_with_one_tool_call()))
    assert recorder.calls == []


def test_result_write_failure_reports_persistence_failed_but_tool_ran() -> None:
    """Spec §C: defence-in-depth on the tool-result write.

    The assistant row persists (first ``append`` succeeds); the tool runs
    and returns success; the tool-result ``append`` raises. ``dispatch_tool_calls``
    must:
      - return ``EffectReceipt(FAILED, error_code="session_persistence_failed")``;
      - leave the journal holding ``[surface/user_message,
        surface/assistant_message{tool_calls=[X]}]`` with NO
        ``surface/tool_result`` (the append failed before the event landed);
      - the tool DID run — the executor was called.

    The journal is consistent: the assistant row precedes (and declares)
    the tool call, so ``derive_messages()`` orphan-drops nothing. The wire
    shape ``[user, assistant{tool_calls=[X]}]`` reaches the model with no
    dangling tool row — the ``drop_orphan_function_calls`` defence-in-depth
    is unverified-by-design on this seam because the failure mode keeps
    the journal clean.
    """
    # ``fail_after=1``: first append (assistant_message) succeeds, second
    # append (tool_result) raises — the scenario this test exercises.
    # The user message is pre-populated under a permissive budget so it
    # does not consume the failure slot reserved for the tool_result.
    session = _FlakySession(fail_after=10**6)
    writer = RunSessionWriter(session=session)
    writer.append_user_message(message_id="u1", role="user", content="hi")
    # Now arm the failure: the next two appends (assistant, tool_result)
    # consume the budget; the assistant succeeds (count→0), the
    # tool_result raises.
    session.fail_after = 1
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

    receipts = asyncio.run(
        body.dispatch_tool_calls(decision=_decision_with_one_tool_call(), state=_state())
    )

    # Receipt is rejected with the persistence-failure code.
    assert isinstance(receipts, list)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert isinstance(receipt, EffectReceipt)
    assert receipt.outcome is EffectOutcome.FAILED
    assert receipt.error_code == "session_persistence_failed"

    # Tool DID run — the executor was invoked before the result append failed.
    assert recorder.calls == [{"name": "echo", "args": {"x": 1}}]

    # Journal: user + assistant_message(tool_calls=[X]); NO surface/tool_result.
    surface_events = [e for e in session.events if e.type.startswith("surface/")]
    assert [e.type for e in surface_events] == [
        "surface/user_message",
        "surface/assistant_message",
    ]
    # The assistant row carries the declared tool_call (no orphan yet).
    assistant_event = surface_events[1]
    assert assistant_event.data["tool_calls"] == [
        {"id": "call-1", "name": "echo", "arguments": '{"x": 1}'}
    ]

    # derive_messages() orphan-drops nothing: the journal is consistent
    # (the assistant row precedes the (never-written) tool_result).
    msgs = writer.derive_messages()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["tool_calls"] == [{"id": "call-1", "name": "echo", "arguments": '{"x": 1}'}]
