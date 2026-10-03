"""Single-producer guard for ``surface/assistant_message``.

``BodySurfaceEventContract`` states the invariant: for every Decision with
N>=1 tool_calls the Session holds exactly 1 ``surface/assistant_message``
carrying all N calls. Two producers satisfied it independently and the
Session kept both rows, so ``derive_messages`` handed the model every one
of its own prior turns twice. A model reads a doubled history as an
instruction and starts doubling its own narration inside a single stream
(``run_56c3352cd22e``: the repeat lands inside one SSE delta, so no
retry or re-assembly on our side can explain it).

The two legs under test are the ones the composition actually wires:

- ``ModelVisibleHookAdapter`` wraps the Brain's LLM via ``instrument_llm``
  and fires on the COMPLETED stream event. It is an observer. Its module
  contract says it holds no truth and writes nothing to disk.
- ``think.llm.persist`` is the graph node that owns the journal write for
  the turn. ``effect.execute`` already assumes the think side wrote the
  assistant row before it appends the matching ``surface/tool_result``.

Both legs receive the writer differently: the node gets it through the
typed runtime carrier, the adapter reaches a read-face ContextVar and
casts it. ADR-0226 §1 rules out the ContextVar lookup for writer
resolution, which is the second reason the observer leg does not own
this fact.

delete-when: N/A (single-owner regression lock, same class as
``test_persist_module_has_no_tool_journal_commit_reference``).
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from lca.contracts.models.core.conversation.llm import (
    LLMResponse,
    LLMStreamEvent,
    LLMStreamEventType,
    NativeToolCall,
    TokenUsage,
)
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.think.llm.persist import LlmPersistExecutor
from lca.plugins.events.hooks.model_visible.adapter import ModelVisibleHookAdapter
from lca.plugins.events.publishers import _session_publish
from lca.runtime.session.run_session_writer import RunSessionWriter
from lca.session.append import Session
from lca.session.lifecycle.bind import RunEventSessionBridge

SURFACE_ASSISTANT = "surface/assistant_message"


class _RuntimeCarrier(dict):
    """Kernel runtime carrier: attribute reads fall through to mapping keys."""

    def __getattr__(self, name: str) -> object:
        return self.get(name)


class _ScriptedLLM(LLMAdapter):
    """One canned response, delivered the way the think path delivers it."""

    name = "scripted-guard-llm"
    model = "test-model"

    def __init__(self, response: LLMResponse) -> None:
        self._response = response

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        del prompt, kwargs
        return self._response

    async def stream(self, prompt: str, **kwargs: Any) -> Any:
        del prompt, kwargs
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=self._response)


class _StubHook:
    """Stands in for ``ModelVisibleHook``: step counter plus no-op captures."""

    def __init__(self) -> None:
        self._step_counter = 1
        self.post_calls = 0

    def capture_pre_llm(self, **kwargs: Any) -> None:
        del kwargs

    def capture_post_llm(self, **kwargs: Any) -> None:
        del kwargs
        self.post_calls += 1


def _response(call_id: str, text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        model="test-model",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
        tool_calls=[
            NativeToolCall(call_id=call_id, name="download", arguments={"file_id": "abc"}),
        ],
    )


def _cursor(run_id: str) -> SimpleNamespace:
    """Snapshot shape ``_snapshot_attrs`` reads; None would skip the hook."""
    return SimpleNamespace(snapshot=SimpleNamespace(run_id=run_id, incarnation=1))


async def _drive_adapter(bridge: RunEventSessionBridge, response: LLMResponse) -> None:
    """Run one streamed LLM call through the observer leg."""
    hook = _StubHook()
    adapter = ModelVisibleHookAdapter(_ScriptedLLM(response), hook)
    events = [e async for e in adapter.stream("prompt", cursor=_cursor(bridge.inner.id))]
    assert any(e.type is LLMStreamEventType.COMPLETED for e in events)
    # The hook swallows post-emit failures, so pin that the leg really ran
    # before reading any absence of rows as evidence.
    assert hook.post_calls == 1


async def _drive_persist(writer: RunSessionWriter, response: LLMResponse, *, step: int) -> None:
    """Run the graph leg that owns the turn's journal write."""
    state = AgentState(trace_id="trace-guard", task="", budget=Budget())
    state.step = step
    await LlmPersistExecutor().node_execute(
        NodeContext(runtime=_RuntimeCarrier(state=state, writer=writer), budget={}, metadata={}),
        NodeInput(port_values={"llm_response": response}),
    )


def _assistant_rows(bridge: RunEventSessionBridge) -> list[Any]:
    return [e for e in bridge.inner.snapshot_events() if e.type == SURFACE_ASSISTANT]


@pytest.fixture
def bridge() -> Any:
    bound = RunEventSessionBridge(Session("run_assistant_surface_guard"))
    _session_publish.set_publish_session(bound)
    try:
        yield bound
    finally:
        _session_publish.reset_publish_session(None)


@pytest.mark.asyncio
async def test_observer_leg_appends_no_assistant_surface_row(bridge: Any) -> None:
    """The adapter hook observes the response; the graph node journals it."""
    await _drive_adapter(bridge, _response("call_1", "找到了！现在下载内容："))

    assert _assistant_rows(bridge) == [], (
        "ModelVisibleHookAdapter wrote surface/assistant_message. The observer "
        "leg and think.llm.persist both own this fact, so derive_messages hands "
        "the model every prior turn twice and the model learns to repeat itself."
    )


@pytest.mark.asyncio
async def test_both_legs_yield_exactly_one_assistant_surface_row(bridge: Any) -> None:
    """Composition invariant: one LLM response, one assistant row."""
    response = _response("call_1", "找到了！现在下载内容：")
    writer = RunSessionWriter(session=bridge.inner)

    await _drive_adapter(bridge, response)
    await _drive_persist(writer, response, step=1)

    rows = _assistant_rows(bridge)
    assert len(rows) == 1, f"expected exactly 1 {SURFACE_ASSISTANT}, got {len(rows)}"
    declared = [tc["id"] for tc in rows[0].data["tool_calls"]]
    assert declared == ["call_1"]


@pytest.mark.asyncio
async def test_derived_history_has_no_doubled_assistant_turn(bridge: Any) -> None:
    """The user-visible symptom: no turn appears twice in the model's history."""
    writer = RunSessionWriter(session=bridge.inner)
    for step, (call_id, text) in enumerate(
        [("call_1", "找到了！现在下载内容："), ("call_2", "文件已找到！让我解析：")], start=1
    ):
        response = _response(call_id, text)
        await _drive_adapter(bridge, response)
        await _drive_persist(writer, response, step=step)

    messages = writer.derive_messages()
    doubled: list[str] = []
    for previous, current in pairwise(messages):
        if previous.get("role") != "assistant" or current.get("role") != "assistant":
            continue
        previous_ids = [tc.get("id") for tc in previous.get("tool_calls") or []]
        current_ids = [tc.get("id") for tc in current.get("tool_calls") or []]
        if previous_ids and previous_ids == current_ids:
            doubled.extend(previous_ids)

    assert not doubled, (
        f"derive_messages returned the same assistant turn twice (call_ids={doubled}); "
        f"roles={[m.get('role') for m in messages]}"
    )


def test_adapter_module_has_no_assistant_surface_producer() -> None:
    """Structural lock behind the behavioural guards above."""
    import lca.plugins.events.hooks.model_visible.adapter as adapter_module

    source = Path(adapter_module.__file__).read_text(encoding="utf-8")
    assert "append_assistant_message" not in source, (
        "the model_visible adapter re-gained a second surface/assistant_message "
        "producer; think.llm.persist is the single owner"
    )
