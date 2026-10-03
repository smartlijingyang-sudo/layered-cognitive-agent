"""A tool call the wire gate refuses must still reach the journal.

``UseToolOperation.execute`` runs three gates before any tool dispatch and
returns the block ``Observation`` straight to the caller. ``SafeExecutor``
is the only emitter of ``step.tool_call.record`` and
``step.tool_result.record``, so a refused call used to leave no journal
fact at all. ``ToolDeriver`` reads exactly those two execution points.
With nothing to read it reports ``tool=ok``, doctor reports a clean run,
and ``debug-run`` reports ``error_ref=(none)``.

``run_56c3352cd22e`` refused 2 of 10 tool calls this way. Both carried
``EffectReceipt(outcome=failed, failure_kind=tool_wire)`` and both were
absent from the run diagnostics, which is why the run read as healthy.

The three gates share one defect, so all three are covered here:
``tool_wire_block_observation`` (truncated or malformed arguments on the
wire), ``unexposed_tool_block_observation`` (deferred namespace not
loaded this turn), and ``missing_arguments_block_observation`` (required
arguments never arrived).

delete-when: N/A (observability regression lock for C3 fact traceability).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lca.cognition.body.actions.action_handlers import UseToolOperation
from lca.cognition.body.tools.tool_batch_execution import (
    SequentialToolBatchExecutionPolicy,
)
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, ToolCall
from lca.contracts.models.core.policy.budget import create_budget
from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.session import (
    ToolDeferSession,
    reset_current_defer_session,
    set_current_defer_session,
)
from lca.plugins.events.publishers import _session_publish
from lca.plugins.observability.health.derivers._spine import SpineEvent
from lca.plugins.observability.health.derivers.tool_deriver import ToolDeriver
from lca.session.append import Session
from lca.session.lifecycle.bind import RunEventSessionBridge

RUN_ID = "run_blocked_tool_call_journal"

DESCRIPTIONS = {
    "core": "推理原语:按需加载工具目录",
    "file": "文件系统:列出、读取、写入、编辑、移动、搜索文件内容",
}


@dataclass
class _Tool:
    name: str
    namespace: str = ""
    parameters: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.description = f"tool {self.name}"
        self.parameters = self.parameters or {"type": "object", "properties": {}}

    async def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        raise AssertionError("a refused call must never reach the tool")


@dataclass
class _Registry:
    tools: dict[str, _Tool]

    def get(self, name: str) -> _Tool | None:
        return self.tools.get(name)


class _NeverRunsExecutor:
    """Every gate under test must short-circuit before dispatch."""

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a wire-gate blocked call must never reach SafeExecutor")


def _decision(call: ToolCall) -> Decision:
    return Decision(
        decision_id="dec-blocked",
        action_type=ActionType.USE_TOOL.value,
        rationale="r",
        confidence=1.0,
        tool_calls=[call],
    )


def _state() -> AgentState:
    return AgentState(trace_id="trace-blocked", task="blocked call", budget=create_budget())


def _payload_of(event: Any) -> dict[str, Any]:
    data = event.data
    inner = data.get("payload") if isinstance(data, dict) and "payload" in data else data
    return dict(inner) if isinstance(inner, dict) else {}


def _facts(bridge: RunEventSessionBridge, ep: str) -> list[dict[str, Any]]:
    return [_payload_of(e) for e in bridge.inner.snapshot_events() if e.type.endswith(ep)]


def _as_spine_events(bridge: RunEventSessionBridge) -> list[SpineEvent]:
    return [
        SpineEvent(
            event_id=f"{RUN_ID}:{e.seq}",
            ts="2026-10-04T00:00:00+00:00",
            run_id=RUN_ID,
            execution_point=e.type.removeprefix("spine."),
            payload=_payload_of(e),
        )
        for e in bridge.inner.snapshot_events()
        if e.type.startswith("spine.")
    ]


@pytest.fixture
def bridge() -> Any:
    bound = RunEventSessionBridge(Session(RUN_ID))
    _session_publish.set_publish_session(bound)
    try:
        yield bound
    finally:
        _session_publish.reset_publish_session(None)


@pytest.fixture
def defer_file_namespace() -> Any:
    """Publish a defer session where ``file`` stays deferred.

    ``memory`` is eager in the shipped policy default, so ``file`` is the
    namespace that is genuinely hidden until ``tool_search`` loads it.
    """
    session = ToolDeferSession(DeferPolicy(namespace_descriptions=DESCRIPTIONS))
    session.update_turn(
        (_Tool("tool_search", namespace="core"), _Tool("readFile", namespace="file"))
    )
    token = set_current_defer_session(session)
    try:
        yield session
    finally:
        reset_current_defer_session(token)


async def _run_blocked(decision: Decision, registry: _Registry) -> Any:
    operation = UseToolOperation(
        registry,
        _NeverRunsExecutor(),
        batch_execution_policy=SequentialToolBatchExecutionPolicy(),
    )
    return await operation.execute(decision, _state())


def _assert_journaled_failure(
    bridge: RunEventSessionBridge,
    *,
    tool_name: str,
    call_id: str,
    failure_kind: str,
    error_fragment: str,
) -> None:
    calls = _facts(bridge, "step.tool_call.record")
    assert len(calls) == 1, f"the refused call left no step.tool_call.record: {calls!r}"
    assert calls[0]["tool_name"] == tool_name
    assert calls[0]["invocation_id"] == call_id

    results = _facts(bridge, "step.tool_result.record")
    assert len(results) == 1, f"the refused call left no step.tool_result.record: {results!r}"
    result = results[0]
    assert result["invocation_id"] == call_id
    assert result["ok"] is False
    assert result["outcome"] == "failure"
    assert result["failure_kind"] == failure_kind
    assert error_fragment in (result.get("error") or "")

    conditions = [c for c in ToolDeriver().evaluate(_as_spine_events(bridge)) if c.type == "tool"]
    assert any(c.status == "degraded" and c.reason == "tool_result_failed" for c in conditions), (
        f"ToolDeriver still reports a refused call as healthy: "
        f"{[(c.status, c.reason) for c in conditions]}"
    )


@pytest.mark.asyncio
async def test_invalid_wire_arguments_are_journaled(bridge: Any) -> None:
    """Gate 1: arguments truncated or malformed on the wire."""
    call = ToolCall(
        call_id="call-wire",
        tool_name="writeFile",
        arguments={},
        wire_status="invalid",
        wire_reason="unterminated_or_truncated_json",
    )

    observation = await _run_blocked(_decision(call), _Registry({}))

    assert observation.success is False
    assert "tool_wire_invalid" in (observation.error or "")
    _assert_journaled_failure(
        bridge,
        tool_name="writeFile",
        call_id="call-wire",
        failure_kind="tool_wire",
        error_fragment="tool_wire_invalid",
    )


@pytest.mark.asyncio
async def test_unloaded_namespace_is_journaled(bridge: Any, defer_file_namespace: Any) -> None:
    """Gate 2: the tool's deferred namespace was not loaded this turn."""
    del defer_file_namespace  # the fixture publishes the session the gate reads
    call = ToolCall(call_id="call-defer", tool_name="readFile", arguments={"path": "/mnt/data"})

    observation = await _run_blocked(
        _decision(call), _Registry({"readFile": _Tool("readFile", namespace="file")})
    )

    assert observation.success is False
    assert "deferred namespace" in (observation.error or "")
    _assert_journaled_failure(
        bridge,
        tool_name="readFile",
        call_id="call-defer",
        failure_kind="tool_wire",
        error_fragment="deferred namespace",
    )


@pytest.mark.asyncio
async def test_missing_required_arguments_are_journaled(bridge: Any) -> None:
    """Gate 3: every required argument is absent."""
    call = ToolCall(call_id="call-args", tool_name="writeFile", arguments={})
    tool = _Tool(
        "writeFile",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )

    observation = await _run_blocked(_decision(call), _Registry({"writeFile": tool}))

    assert observation.success is False
    assert "missing_required_arguments" in (observation.error or "")
    _assert_journaled_failure(
        bridge,
        tool_name="writeFile",
        call_id="call-args",
        failure_kind="tool_wire",
        error_fragment="missing_required_arguments",
    )
