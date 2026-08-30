"""Production run owner streams Journal live SSE; chat completions stay housekeeping.

The empty ``[DONE]`` stub on ``SessionRunAdapter`` was the live-path failure:
tests used to inject ``RegistryRunAdapter`` while ``create_app()`` composed a
different owner. These tests drive the **default** composition.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from gateway.app import create_app
from gateway.runs.legacy_adapter import RegistryRunAdapter
from gateway.runs.session import RunRegistry, RunSession
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    ReasoningDelta,
    RunScope,
    StampedEvent,
    StepTextDelta,
    ToolInvoked,
    ToolStarted,
)
from lca.infrastructure.observability.journal.live_tail import LiveTail
from tests.support.gateway_app import create_scripted_app

_SEQ = [0]


def _stamped(payload: Any) -> StampedEvent:
    _SEQ[0] += 1
    seq = _SEQ[0]
    return StampedEvent(
        seq=seq,
        ts=float(seq),
        scope=RunScope(trace_id="t", run_id="r"),
        event_type=type(payload).__name__,
        data={},
        event=payload,
    )


def _seed_journal(registry: RunRegistry, run_id: str = "run-prod-sse") -> RunSession:
    tail = LiveTail()
    session = RunSession(
        run_id=run_id,
        trace_id=f"trace-{run_id}",
        jsonl_path=Path("/var/data/lca-nonexistent.jsonl"),
        tail=tail,
        question="hello",
        user_text="hello",
        mode="solo",
    )
    registry.put(session)
    tail.on_event(_stamped(ReasoningDelta(text_delta="think-token")))
    tail.on_event(
        _stamped(
            ToolStarted(
                tool_name="read_file",
                invocation_id="call-prod",
                arguments={"path": "/var/data/x"},
            )
        )
    )
    tail.on_event(
        _stamped(
            ToolInvoked(
                tool_name="read_file",
                invocation_id="call-prod",
                ok=True,
            )
        )
    )
    tail.on_event(_stamped(StepTextDelta(text_delta="answer-token", channel="answer")))
    tail.on_event(_stamped(AgentRunFinished(status="completed")))
    tail.close()
    return session


def test_session_run_adapter_is_not_on_the_chat_path() -> None:
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("gateway.runs.session_adapter")


def test_default_create_app_run_port_is_registry_not_session_stub() -> None:
    application = create_app(lifespan=lambda _app: None)
    port = application.state.run_port
    assert type(port).__name__ == "RegistryRunAdapter"
    assert isinstance(port, RegistryRunAdapter)
    assert type(port).__name__ != "SessionRunAdapter"
    assert application.state.run_registry is not None


@pytest.mark.asyncio
async def test_production_owner_stream_run_live_is_not_empty() -> None:
    application = create_app(lifespan=lambda _app: None)
    registry = application.state.run_registry
    session = _seed_journal(registry, run_id="run-owner-stream")
    frames: list[bytes] = []
    async for line in application.state.run_port.stream_run_live(session.run_id, 0):
        if line:
            frames.append(line)
    body = b"".join(frames).decode("utf-8")
    assert "event: ReasoningDelta" in body
    assert "event: StepTextDelta" in body
    assert "event: ToolStarted" in body
    assert "event: AgentRunFinished" in body
    assert "think-token" in body
    assert "answer-token" in body
    assert "read_file" in body
    assert "data: [DONE]" not in body
    assert "chat.completion" not in body


def test_production_v1_chat_completions_stream_is_housekeeping() -> None:
    app = create_scripted_app()
    spy = AsyncMock()
    app.state.run_port.create_and_dispatch = spy

    with (
        TestClient(app) as client,
        patch(
            "gateway.openai_housekeeping.create_simple_completion",
            new=AsyncMock(
                return_value=("topic title", {"prompt_tokens": 1, "completion_tokens": 2})
            ),
        ),
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "solo",
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
    spy.assert_not_called()
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    body = response.content.decode("utf-8")
    assert "chat.completion.chunk" in body
    assert "topic title" in body
    assert "data: [DONE]" in body
    assert "event: ReasoningDelta" not in body
    assert "event: StepTextDelta" not in body
    assert "think-token" not in body
    assert "answer-token" not in body
