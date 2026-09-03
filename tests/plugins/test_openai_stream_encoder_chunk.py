"""Tests for OpenAI ChatCompletion chunk line builder (ADR-0099 Phase 1.1)."""

from __future__ import annotations

import json

import pytest

from lca.plugins.transport.openai_stream_encoder__chunk_provider import OpenAIChatChunkBuilder


@pytest.fixture
def builder() -> OpenAIChatChunkBuilder:
    return OpenAIChatChunkBuilder(model="solo")


def _parse_data_line(line_bytes: bytes) -> dict:
    """Decode ``data: {...}\\n\\n`` and return the JSON payload."""
    text = line_bytes.decode("utf-8")
    assert text.startswith("data: ")
    assert text.endswith("\n\n")
    payload = text[len("data: ") :].rstrip("\n")
    return json.loads(payload)


def test_append_content_emits_object_chat_completion_chunk(builder):
    line = _parse_data_line(builder.append_content("Hi"))
    assert line["object"] == "chat.completion.chunk"
    assert line["model"] == "solo"
    assert line.get("id")
    choice = line["choices"][0]
    assert choice["delta"]["role"] == "assistant"
    assert choice["delta"]["content"] == "Hi"
    assert choice["finish_reason"] is None


def test_append_reasoning_uses_reasoning_content_field(builder):
    line = _parse_data_line(builder.append_reasoning("thinking…"))
    choice = line["choices"][0]
    assert choice["delta"]["reasoning_content"] == "thinking…"
    assert "content" not in choice["delta"]


def test_start_tool_call_emits_index_id_name_and_arguments(builder):
    line = _parse_data_line(
        builder.start_tool_call(
            index=0, call_id="call_xyz", name="read_file", arguments_json='{"path":"/var/data/x"}'
        )
    )
    choice = line["choices"][0]
    tool = choice["delta"]["tool_calls"][0]
    assert tool["index"] == 0
    assert tool["id"] == "call_xyz"
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "read_file"
    assert json.loads(tool["function"]["arguments"]) == {"path": "/var/data/x"}


def test_finish_reason_stop_terminates_chunk(builder):
    line = _parse_data_line(builder.finish_reason("stop"))
    choice = line["choices"][0]
    assert choice["delta"] == {}
    assert choice["finish_reason"] == "stop"


def test_done_emits_sentinel(builder):
    assert builder.done() == b"data: [DONE]\n\n"


def test_content_chunks_share_response_id(builder):
    """OpenAI clients key off ``id`` to dedupe; the builder must keep one."""
    line_a = _parse_data_line(builder.append_content("a"))
    line_b = _parse_data_line(builder.append_content("b"))
    assert line_a["id"] == line_b["id"]
    assert line_a["object"] == line_b["object"] == "chat.completion.chunk"


def test_appender_round_trip_with_chinese_token(builder):
    line = _parse_data_line(builder.append_content("你好,世界"))
    assert line["choices"][0]["delta"]["content"] == "你好,世界"
