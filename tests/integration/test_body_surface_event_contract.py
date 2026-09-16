"""Spec §G-16: BodySurfaceEventContract — multi-call decisions.

PR-2 closes B-1 (orphan-drop in multi-call decisions). The contract is
stated in one line: ``For every decision with N>=1 tool_calls, the
Session MUST contain exactly 1 surface/assistant_message with all N
tool_calls, followed by N surface/tool_result messages``.

The 3 tests in this file exercise the canonical 3-tool-call decision
shape end-to-end through ``SimpleBody.dispatch_tool_calls`` against a
minimal ``SessionProtocol`` fixture:

- ``test_one_assistant_message_per_decision`` — Decision with 3
  tool_calls yields exactly 1 ``surface/assistant_message`` row, with
  all 3 declared in its ``tool_calls`` payload.
- ``test_n_tool_results_per_decision`` — same Decision yields exactly
  3 ``surface/tool_result`` rows, one per call.
- ``test_orphan_drop_count_is_zero_for_multi_call`` — orphan-drop
  (spec §D defence-in-depth) keeps all 3 results; the runtime counter
  introduced by G-17 stays at 0.

Initial run (pre-PR-2): all 3 fail — ``dispatch_tool_call`` only
commits the first call and orphan-drop eats the rest.
Post-PR-2: all 3 pass — the renamed ``dispatch_tool_calls`` commits the
batch and orphan-drop has no work to do.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from lca.cognition.body.executor.simple_body import SimpleBody
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, ToolCall
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
class _InMemorySession:
    events: list[_StoredEvent] = field(default_factory=list)
    system: str | None = None
    next_seq: int = 0

    def append(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        surface_op: Any | None = None,
        source_event_seqs: tuple[int, ...] | None = None,
    ) -> _StoredEvent:
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
        if self.system is None:
            return None
        from lca.contracts.models.session.epoch_header import EpochHeader

        return EpochHeader(system=self.system)

    @property
    def id(self) -> str:
        return "test-session"


# ── Minimal Tool / SafeExecutor / ToolRegistry fakes ────────────────────────


@dataclass
class _FakeTool:
    name: str

    async def execute(self, args: dict[str, Any]) -> Any:
        from lca.contracts.atoms.ids.ids import new_id
        from lca.contracts.models.core.execution.decision import Observation

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


def _three_call_decision() -> Decision:
    return Decision(
        decision_id="dec-multi-3",
        action_type=ActionType.USE_TOOL.value,
        rationale="multi-call",
        confidence=1.0,
        tool_calls=[
            ToolCall(call_id="call-A", tool_name="runCommand", arguments={"cmd": "a"}),
            ToolCall(call_id="call-B", tool_name="runCommand", arguments={"cmd": "b"}),
            ToolCall(call_id="call-C", tool_name="runCommand", arguments={"cmd": "c"}),
        ],
    )


def _body(writer: RunSessionWriter) -> SimpleBody:
    registry = _FakeToolRegistry(
        tools={"runCommand": _FakeTool(name="runCommand")},
    )
    return SimpleBody(
        tool_registry=registry,  # type: ignore[arg-type]
        safe_executor=_FakeSafeExecutor(),  # type: ignore[arg-type]
        transport_registry=None,  # type: ignore[arg-type]
        action_registry=None,  # type: ignore[arg-type]
        writer=writer,
    )


# ── Contract tests ─────────────────────────────────────────────────────────


def test_one_assistant_message_per_decision() -> None:
    """A Decision with 3 tool_calls MUST commit exactly 1 surface/assistant_message.

    The single assistant row carries all 3 declared tool_calls in its
    ``tool_calls`` payload (spec §G-16 invariant).
    """
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    body = _body(writer)
    writer.append_user_message(message_id="u1", role="user", content="do three things")

    receipts = asyncio.run(body.dispatch_tool_calls(decision=_three_call_decision()))

    # Body returns one EffectReceipt per call (per-call semantics).
    assert isinstance(receipts, list)
    assert len(receipts) == 3

    surface_events = [e for e in session.events if e.type.startswith("surface/")]
    assistant_events = [e for e in surface_events if e.type == "surface/assistant_message"]
    assert len(assistant_events) == 1

    declared = assistant_events[0].data["tool_calls"]
    assert [tc["id"] for tc in declared] == ["call-A", "call-B", "call-C"]


def test_n_tool_results_per_decision() -> None:
    """A Decision with 3 tool_calls MUST commit exactly 3 surface/tool_result rows.

    Each tool_result is linked by ``tool_call_id`` to its declared call.
    """
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    body = _body(writer)
    writer.append_user_message(message_id="u1", role="user", content="do three things")

    asyncio.run(body.dispatch_tool_calls(decision=_three_call_decision()))

    surface_events = [e for e in session.events if e.type.startswith("surface/")]
    result_events = [e for e in surface_events if e.type == "surface/tool_result"]
    assert len(result_events) == 3

    result_call_ids = {e.data["tool_call_id"] for e in result_events}
    assert result_call_ids == {"call-A", "call-B", "call-C"}


def test_orphan_drop_count_is_zero_for_multi_call() -> None:
    """A valid multi-call Decision has zero orphans at ``derive_messages`` time.

    spec §D orphan-drop must keep all 3 results because the assistant
    row declared every call. This is the defence-in-depth that PR-2's
    upstream fix relies on: when the Body commits the batch correctly,
    orphan-drop never has work to do.
    """
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    body = _body(writer)
    writer.append_user_message(message_id="u1", role="user", content="do three things")

    asyncio.run(body.dispatch_tool_calls(decision=_three_call_decision()))

    msgs = writer.derive_messages()

    # Wire shape: user, assistant{tool_calls=[A,B,C]}, then 3 tool rows.
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant", "tool", "tool", "tool"]

    # Every tool row's tool_call_id was declared by the assistant row.
    tool_call_ids = {m["tool_call_id"] for m in msgs if m["role"] == "tool"}
    assert tool_call_ids == {"call-A", "call-B", "call-C"}
