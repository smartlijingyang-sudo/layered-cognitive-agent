"""Tests for OpenAIStreamEncoder (ADR-0099 Phase 1.2).

Exercises the journal -> OpenAI ChatCompletion SSE translation by
driving the encoder with the actual ``JournalEvent`` dataclasses
emitted by ``record()``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    ReasoningCompleted,
    ReasoningDelta,
    StepTextDelta,
    ToolDenied,
    ToolInvoked,
    ToolStarted,
)
from lca.plugins.transport.openai_stream_encoder__encoder_provider import OpenAIStreamEncoder
from lca.plugins.transport.openai_stream_encoder__chunk_provider import OpenAIChatChunkBuilder


async def _to_list(stream: AsyncIterator[bytes]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    async for line in stream:
        text = line.decode("utf-8")
        if text.startswith("data: [DONE]"):
            out.append({"_done": True})
            continue
        if not text.startswith("data: "):
            continue
        payload = text[len("data: ") :].rstrip("\n")
        out.append(json.loads(payload))
    return out


def _events(*items: Any) -> AsyncIterator[Any]:
    async def _gen() -> AsyncIterator[Any]:
        for it in items:
            yield it

    return _gen()


@pytest.fixture
def builder() -> OpenAIChatChunkBuilder:
    return OpenAIChatChunkBuilder(model="solo")


@pytest.fixture
def encoder() -> OpenAIStreamEncoder:
    return OpenAIStreamEncoder()


@pytest.mark.asyncio
async def test_reasoning_delta_becomes_reasoning_content(encoder, builder) -> None:
    stream = _events(ReasoningDelta(text_delta="t1"))
    frames = await _to_list(encoder.encode(stream, chunk_builder=builder))
    assert '"reasoning_content": "t1"' in json.dumps(frames[0])
    assert frames[-1]["_done"] is True


@pytest.mark.asyncio
async def test_reasoning_completed_emits_no_chunk(encoder, builder) -> None:
    stream = _events(ReasoningCompleted())
    frames = await _to_list(encoder.encode(stream, chunk_builder=builder))
    # only the trailing [DONE] should appear
    assert len(frames) == 1
    assert frames[0]["_done"] is True


@pytest.mark.asyncio
async def test_step_text_delta_becomes_content(encoder, builder) -> None:
    stream = _events(StepTextDelta(text_delta="hi", channel="answer"))
    frames = await _to_list(encoder.encode(stream, chunk_builder=builder))
    assert '"content": "hi"' in json.dumps(frames[0])
    assert frames[-1]["_done"] is True


@pytest.mark.asyncio
async def test_step_text_delta_decision_channel_dropped(encoder, builder) -> None:
    stream = _events(StepTextDelta(text_delta="hidden", channel="decision"))
    frames = await _to_list(encoder.encode(stream, chunk_builder=builder))
    # only the [DONE] sentinel
    assert len(frames) == 1
    assert frames[0]["_done"] is True


@pytest.mark.asyncio
async def test_tool_started_emits_content_not_tool_calls(encoder, builder) -> None:
    stream = _events(
        ToolStarted(
            tool_name="read_file",
            invocation_id="inv-1",
            arguments={"path": "/var/data/x"},
        )
    )
    frames = await _to_list(encoder.encode(stream, chunk_builder=builder))
    joined = json.dumps(frames)
    assert "read_file" in joined
    assert "/var/data/x" in joined
    assert "tool_calls" not in joined


@pytest.mark.asyncio
async def test_tool_started_then_invoked_emits_content_not_tool_calls(encoder, builder) -> None:
    stream = _events(
        ToolStarted(
            tool_name="read_file", invocation_id="inv-2", arguments={"path": "/var/data/y"}
        ),
        ToolInvoked(
            tool_name="read_file",
            invocation_id="inv-2",
            ok=True,
        ),
        AgentRunFinished(),
    )
    frames = await _to_list(encoder.encode(stream, chunk_builder=builder))
    assert frames[-1]["_done"] is True
    joined = json.dumps(frames)
    assert "tool_calls" not in joined
    # ADR-0101 PR-2:ToolInvoked.output_text 字段已删除;encoder 输出不再
    # 携带原始 file contents here(走 evidence 平面 output_ref)。
    assert "_tool completed_" in joined
    assert '"finish_reason": "stop"' in joined


@pytest.mark.asyncio
async def test_tool_denied_emits_denied_marker(encoder, builder) -> None:
    stream = _events(
        ToolStarted(
            tool_name="write_file",
            invocation_id="inv-3",
            arguments={"path": "/var/data/z"},
        ),
        ToolDenied(tool_name="write_file", reason="permission denied"),
        AgentRunFinished(),
    )
    frames = await _to_list(encoder.encode(stream, chunk_builder=builder))
    joined = json.dumps(frames)
    assert "tool denied" in joined.lower()
    assert "permission denied" in joined


@pytest.mark.asyncio
async def test_agent_run_finished_emits_finish_reason(encoder, builder) -> None:
    stream = _events(
        StepTextDelta(text_delta="hi", channel="answer"),
        AgentRunFinished(status="completed"),
    )
    frames = await _to_list(encoder.encode(stream, chunk_builder=builder))
    assert any('"finish_reason": "stop"' in json.dumps(f) for f in frames if not f.get("_done"))
    assert frames[-1]["_done"] is True


@pytest.mark.asyncio
async def test_two_tools_emit_content_without_tool_calls(encoder, builder) -> None:
    stream = _events(
        ToolStarted(tool_name="read_file", invocation_id="inv-a", arguments={"path": "/x"}),
        ToolInvoked(tool_name="read_file", invocation_id="inv-a", ok=True),
        ToolStarted(tool_name="read_file", invocation_id="inv-b", arguments={"path": "/y"}),
        ToolInvoked(tool_name="read_file", invocation_id="inv-b", ok=True),
        AgentRunFinished(),
    )
    frames = await _to_list(encoder.encode(stream, chunk_builder=builder))
    joined = json.dumps(frames)
    assert "tool_calls" not in joined
    assert "/x" in joined and "/y" in joined


@pytest.mark.asyncio
async def test_lobehub_native_parser_sees_scripted_tokens_on_shipped_encoder(
    encoder: OpenAIStreamEncoder, builder: OpenAIChatChunkBuilder
) -> None:
    """LobeHub openai.ts fields — not a second translator — on encoder bytes."""
    from tests.support.lobehub_openai_sse import (
        lobehub_llm_result_would_call_tool,
        parse_lobehub_openai_sse,
    )

    raw = b"".join(
        [
            line
            async for line in encoder.encode(
                _events(
                    ReasoningDelta(text_delta="why "),
                    ReasoningDelta(text_delta="this"),
                    ToolStarted(
                        tool_name="read_file",
                        invocation_id="call-sim",
                        arguments={"path": "/p"},
                    ),
                    ToolInvoked(
                        tool_name="read_file",
                        invocation_id="call-sim",
                        ok=True,
                    ),
                    StepTextDelta(text_delta="hello ", channel="answer"),
                    StepTextDelta(text_delta="world", channel="answer"),
                    AgentRunFinished(status="completed"),
                ),
                chunk_builder=builder,
            )
        ]
    )
    view = parse_lobehub_openai_sse(raw)
    assert view.done is True
    assert view.reasoning_content == "why this"
    assert "hello world" in view.content
    assert "read_file" in view.content
    # ADR-0101 PR-2:ToolInvoked.output_text 字段已删除;encoder 输出不再
    # 携带原始 body 文本(走 evidence 平面 output_ref)。
    assert "_tool completed_" in view.content
    assert view.tool_calls == []
    assert lobehub_llm_result_would_call_tool(view) is False
    assert view.finish_reasons == ["stop"]
    assert view.custom_event_names == []
    assert view.digest_indirect_frames == []
    assert "content_ref" not in raw.decode("utf-8")


def test_openai_tool_calls_chunk_would_enter_lobehub_call_tool() -> None:
    """Shipped chunk builder still can emit tool_calls; LobeHub would execute them.

    This is the AgentRuntime contract the encoder must not trigger: native
    ``hasToolsCalling`` is ``toolsCalling.length > 0``.
    """
    from tests.support.lobehub_openai_sse import (
        lobehub_llm_result_would_call_tool,
        parse_lobehub_openai_sse,
    )

    builder = OpenAIChatChunkBuilder(model="solo")
    raw = (
        builder.start_tool_call(
            index=0,
            call_id="call-x",
            name="read_file",
            arguments_json='{"path":"/p"}',
        )
        + builder.finish_reason("stop")
        + builder.done()
    )
    view = parse_lobehub_openai_sse(raw)
    assert view.tool_calls
    assert lobehub_llm_result_would_call_tool(view) is True
