"""Spec §D: orphan tool_result dropped before LLM call sees the wire shape.

A tool/result message whose ``tool_call_id`` is not present in any preceding
``assistant{tool_calls=[...]}`` row is an orphan. OpenAI's
``drop_orphan_function_calls`` pattern drops such rows at every LLM-call
preparation step so the wire shape never carries a dangling tool row.

The integration test drives ``RunSessionWriter`` against a minimal
``SessionProtocol`` and asserts that ``derive_messages()`` drops the
orphan before any caller sees the messages list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.runtime.session.run_session_writer import RunSessionWriter


@dataclass
class _StoredEvent:
    """Minimal SessionEvent shape for the writer test fixture."""

    type: str
    seq: int
    time: float
    data: dict[str, Any]
    surface_op: Any | None
    source_event_seqs: tuple[int, ...] | None


@dataclass
class _StoredHeader:
    """Minimal EpochHeader shape for ``request_header`` returns."""

    system: str | None


@dataclass
class _InMemorySession:
    """Minimal ``SessionProtocol`` for the writer test.

    Tracks every ``append`` call in ``events`` and exposes
    ``snapshot_events`` for ``derive_messages`` to walk. Mirrors the shape
    of :class:`lca.session.append.Session` minus durability + observers
    (not needed for orphan-drop projection).
    """

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

    def request_header(self) -> _StoredHeader | None:
        if self.system is None:
            return None
        return _StoredHeader(system=self.system)

    @property
    def id(self) -> str:
        return "test-session"


def test_orphan_tool_result_dropped_at_history_assemble() -> None:
    """[user, assistant{tool_calls=[X]}, tool{call_id=Y}] → orphan tool{Y} dropped.

    The assistant declared ``tool_calls=[X]``; the tool result has
    ``call_id=Y`` — a never-declared tool call. ``derive_messages`` must
    drop the tool row before it reaches the model-visible list.
    """
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    writer.append_user_message(message_id="u1", role="user", content="hi")
    writer.append_assistant_message(
        turn=0,
        step=0,
        role="assistant",
        content=None,
        tool_calls=[{"id": "X", "name": "bash", "arguments": "{}"}],
        usage=None,
    )
    # Orphan: tool result with call_id="Y" that does not match the
    # assistant's declared tool call id "X".
    writer.append_tool_result(turn=0, step=0, call_id="Y", content="orphan", error=None, meta=None)

    msgs = writer.derive_messages()

    # Orphan dropped; only user + assistant remain in the wire shape.
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    # Assistant preserved with its declared tool_call (orphan-drop only
    # touches tool/result rows, not assistant rows).
    assert msgs[1]["tool_calls"] == [{"id": "X", "name": "bash", "arguments": "{}"}]


def test_non_orphan_tool_result_preserved() -> None:
    """[user, assistant{tool_calls=[X]}, tool{call_id=X}] → tool{X} preserved.

    Sanity check: orphan-drop is conservative; matched tool_call_id rows
    stay in the wire shape.
    """
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    writer.append_user_message(message_id="u1", role="user", content="hi")
    writer.append_assistant_message(
        turn=0,
        step=0,
        role="assistant",
        content=None,
        tool_calls=[{"id": "X", "name": "bash", "arguments": "{}"}],
        usage=None,
    )
    writer.append_tool_result(turn=0, step=0, call_id="X", content="ok", error=None, meta=None)

    msgs = writer.derive_messages()

    assert [m["role"] for m in msgs] == ["user", "assistant", "tool"]
    assert msgs[2]["tool_call_id"] == "X"


def test_orphan_tool_result_without_assistant_kept_in_journal_but_dropped_at_wire() -> None:
    """Orphan tool result stays in the journal for provenance, but drops at derive_messages.

    The journal holds the orphan event (so callers can debug the failure
    path); the wire shape projected by ``derive_messages`` does not.
    """
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    writer.append_user_message(message_id="u1", role="user", content="hi")
    writer.append_tool_result(turn=0, step=0, call_id="Z", content="orphan", error=None, meta=None)

    # Journal holds the orphan event (provenance + audit trail).
    assert any(e.type == "surface/tool_result" for e in session.events)

    msgs = writer.derive_messages()

    # But the wire shape drops it (no preceding assistant declared tool_calls).
    assert [m["role"] for m in msgs] == ["user"]


def test_orphan_dropped_count_increments_for_orphan() -> None:
    """Spec §G-17: ``orphan_dropped_count`` increments by 1 per orphan row.

    Pre-PR-2 the count was hidden; PR-2 exposes it on the writer so
    ``RunHealthReport`` (and on-call engineers) can spot a regression in
    the upstream ``Body.dispatch_tool_calls`` seam without scraping logs.
    """
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    writer.append_user_message(message_id="u1", role="user", content="hi")
    writer.append_assistant_message(
        turn=0,
        step=0,
        role="assistant",
        content=None,
        tool_calls=[{"id": "X", "name": "bash", "arguments": "{}"}],
        usage=None,
    )
    # Orphan: call_id="Y" never declared.
    writer.append_tool_result(turn=0, step=0, call_id="Y", content="orphan", error=None, meta=None)

    assert writer.orphan_dropped_count == 0
    writer.derive_messages()
    assert writer.orphan_dropped_count == 1


def test_empty_tool_payload_renders_its_classified_error() -> None:
    """A zero-length result must reach the model as the error text.

    ``run_71456ce99914`` appended two ``role=tool`` rows with empty
    content for two ~33 s sandbox timeouts. The journal keeps payload and
    classification split; ``derive_messages`` is the single projection
    that joins them, and an empty row is indistinguishable from an
    unanswered call — the model re-issues it.
    """
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    writer.append_user_message(message_id="u1", role="user", content="find the file")
    writer.append_assistant_message(
        turn=0,
        step=0,
        role="assistant",
        content=None,
        tool_calls=[{"id": "X", "name": "runCommand", "arguments": "{}"}],
        usage=None,
    )
    writer.append_tool_result(
        turn=0,
        step=0,
        call_id="X",
        content="",
        error={"kind": "execution", "message": "sandbox timed out after 33s", "retryable": True},
        meta=None,
    )

    row = writer.derive_messages()[-1]

    assert row["role"] == "tool"
    assert row["tool_call_id"] == "X"
    assert row["content"].strip()
    assert "sandbox timed out after 33s" in row["content"]
    assert "retryable=True" in row["content"]


def test_successful_tool_without_output_states_it_explicitly() -> None:
    """Success with no payload is a fact, not a blank the model must guess at."""
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    writer.append_assistant_message(
        turn=0,
        step=0,
        role="assistant",
        content=None,
        tool_calls=[{"id": "X", "name": "writeFile", "arguments": "{}"}],
        usage=None,
    )
    writer.append_tool_result(turn=0, step=0, call_id="X", content="", error=None, meta=None)

    row = writer.derive_messages()[-1]

    assert row["content"] == "[tool_result] (no output)"


def test_orphan_dropped_count_is_zero_for_valid_multi_call() -> None:
    """Spec §G-17: post-PR-2 a valid multi-call decision leaves the counter at 0.

    Drives ``SimpleBody.dispatch_tool_calls`` end-to-end with 5
    ``runCommand`` calls (the B-1 scenario from ``run_feb0f21ee770``)
    and asserts the counter stays at 0 because every ``call_id`` was
    declared by the single assistant row before any tool ran.
    """
    import asyncio

    from lca.cognition.body.executor.simple_body import SimpleBody
    from lca.contracts.atoms.enums.enums import ActionType
    from lca.contracts.models.core.execution.decision import Decision, ToolCall
    from lca.contracts.models.team.role.team import CacheConfig, RetryPolicy
    from lca.contracts.protocols.runtime.infra.infra import Tool

    @dataclass
    class _Tool:
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
    class _Registry:
        tools: dict[str, Tool] = field(default_factory=dict)

        def get(self, name: str) -> Tool | None:
            return self.tools.get(name)

    @dataclass
    class _SafeExecutor:
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

    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    body = SimpleBody(
        tool_registry=_Registry(tools={"runCommand": _Tool(name="runCommand")}),  # type: ignore[arg-type]
        safe_executor=_SafeExecutor(),  # type: ignore[arg-type]
        transport_registry=None,  # type: ignore[arg-type]
        action_registry=None,  # type: ignore[arg-type]
        writer=writer,
    )
    writer.append_user_message(message_id="u1", role="user", content="do five things")
    decision = Decision(
        decision_id="dec-multi-5",
        action_type=ActionType.USE_TOOL.value,
        rationale="multi-call",
        confidence=1.0,
        tool_calls=[
            ToolCall(call_id=f"call-{i}", tool_name="runCommand", arguments={"i": i})
            for i in range(5)
        ],
    )

    asyncio.run(body.dispatch_tool_calls(decision=decision))
    msgs = writer.derive_messages()

    # Wire shape: user, assistant{tool_calls=[5]}, then 5 tool rows.
    assert [m["role"] for m in msgs] == [
        "user",
        "assistant",
        "tool",
        "tool",
        "tool",
        "tool",
        "tool",
    ]
    # PR-2 G-17: orphan_dropped_count stays 0 for any well-formed multi-call.
    assert writer.orphan_dropped_count == 0


def test_multi_call_turn_via_effect_execute_answers_every_call_id() -> None:
    """Production seam, end to end: N declared calls ⇒ N ``role=tool`` rows.

    Drives the shipped nodes — ``act.envelope`` mints one envelope per
    call, ``ToolBatchExecutor`` executes the batch and packages per-call
    facts, ``effect.execute`` surfaces them, and the real
    ``RunSessionWriter.derive_messages`` projects the wire shape. This is
    the loop ``run_71456ce99914`` broke: two ``activate_skill`` calls
    executed, neither result reached the next request, so the model
    re-issued the identical pair.
    """
    import asyncio

    from lca.cognition.body.tools.tool_batch_executor import ToolBatchExecutor
    from lca.contracts.atoms.enums.enums import ActionType
    from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall
    from lca.contracts.protocols.declarative.declarative_1.node_executor import (
        NodeContext,
        NodeInput,
    )
    from lca.nodes.act.envelope.envelope import ActEnvelopeExecutor
    from lca.nodes.concept.effect.execute import EffectExecuteExecutor

    @dataclass
    class _Tool:
        name: str
        description: str = ""
        parameters: dict[str, Any] = field(default_factory=dict)
        is_idempotent: bool = True

    @dataclass
    class _Registry:
        tools: dict[str, Any] = field(default_factory=dict)

        def get(self, name: str) -> Any:
            return self.tools.get(name)

    @dataclass
    class _SafeExecutor:
        async def execute(
            self,
            tool: Any,
            args: dict[str, Any],
            retry_policy: Any,
            cache_config: Any,
            invocation_id: str = "",
        ) -> Observation:
            del retry_policy, cache_config
            from lca.contracts.atoms.ids.ids import new_id

            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload=f"activated {args.get('skill_id')} via {tool.name}",
                tool_call_id=invocation_id,
            )

    @dataclass
    class _Gateway:
        aggregate: Any

        async def execute(self, envelope: Any, policy: Any, **kwargs: Any) -> Any:
            return {"result": self.aggregate, "invocation_id": "inv"}

    @dataclass
    class _Runtime:
        writer: Any
        effect_gateway: Any
        state: Any = None

        def get(self, key: str, default: Any = None) -> Any:
            return getattr(self, key, default)

    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    decision = Decision(
        decision_id="dec-multi-2",
        action_type=ActionType.USE_TOOL.value,
        rationale="activate both skills",
        confidence=1.0,
        tool_calls=[
            ToolCall(
                call_id="call-office",
                tool_name="activate_skill",
                arguments={"skill_id": "officecli"},
            ),
            ToolCall(call_id="call-pdf", tool_name="activate_skill", arguments={"skill_id": "pdf"}),
        ],
    )

    async def _drive() -> None:
        envelope_ctx = NodeContext(
            runtime=_Runtime(writer=writer, effect_gateway=None),
            budget={},
            metadata={"plan_ref": "act.subgraph", "node_id": "act.envelope"},
        )
        envelopes = (
            await ActEnvelopeExecutor().node_execute(
                envelope_ctx, NodeInput(port_values={"decision": decision, "state": None})
            )
        ).port_values["envelopes"]

        aggregate = await ToolBatchExecutor(
            _Registry(tools={"activate_skill": _Tool(name="activate_skill")}),
            _SafeExecutor(),
        ).execute(decision.tool_calls)

        # The think side stages the assistant row declaring both calls
        # before any tool runs (persist-before-execute).
        writer.append_assistant_message(
            turn=0,
            step=0,
            role="assistant",
            content=None,
            tool_calls=[
                {"id": call.call_id, "name": call.tool_name, "arguments": "{}"}
                for call in decision.tool_calls
            ],
            usage=None,
        )
        # Production dispatches envelopes[0] per act visit while the batch
        # executor runs every declared call.
        await EffectExecuteExecutor().node_execute(
            NodeContext(
                runtime=_Runtime(writer=writer, effect_gateway=_Gateway(aggregate)),
                budget={},
                metadata={"plan_ref": "act.subgraph", "node_id": "effect.execute"},
            ),
            NodeInput(port_values={"envelope": envelopes[0], "decision": decision, "state": None}),
        )

    asyncio.run(_drive())
    msgs = writer.derive_messages()

    assert [m["role"] for m in msgs] == ["assistant", "tool", "tool"]
    assert [m["tool_call_id"] for m in msgs[1:]] == ["call-office", "call-pdf"]
    assert all(m["content"].strip() for m in msgs[1:])
    assert "officecli" in msgs[1]["content"]
    assert "pdf" in msgs[2]["content"]
    assert writer.orphan_dropped_count == 0
