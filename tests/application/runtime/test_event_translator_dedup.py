"""Tests for EventTranslator stream deduplication (INV-01).

Guarantees that when streaming tokens are emitted via ``llm.stream.token``,
the subsequent ``llm.request.header.assistant`` containing full assistant text
is NOT re-appended, preventing doubled responses in the chat UI.
"""

from __future__ import annotations

from lca.application.runtime.coordinator.event_translator import EventTranslator


def test_stream_token_followed_by_header_assistant_does_not_duplicate() -> None:
    t = EventTranslator()

    # 1. LLM call start
    start_ev = {
        "event": {
            "execution_point": "llm.call.start",
            "payload": {"model": "solo", "stream": True},
        }
    }
    out_start = t.translate(start_ev)
    assert out_start[0]["type"] == "stream_start"

    # 2. Token streamed incrementally
    token_ev = {
        "event": {
            "execution_point": "llm.stream.token",
            "payload": {"text_delta": "你好！我是架构小助", "channel_kind": "output"},
        }
    }
    out_token = t.translate(token_ev)
    assert out_token[0]["type"] == "stream_chunk"
    assert out_token[0]["data"]["content"] == "你好！我是架构小助"

    # 3. LLM call end
    end_ev = {
        "event": {
            "execution_point": "llm.call.end",
            "payload": {"model": "solo", "stream": True, "outcome": "success"},
        }
    }
    out_end = t.translate(end_ev)
    assert isinstance(out_end, list)
    assert [item["type"] for item in out_end] == ["stream_end", "visible_output_end"]

    # 4. Header assistant arrives carrying the FULL assistant text.
    # Because tokens were already streamed, this event MUST return None to avoid duplication!
    header_ev = {
        "event": {
            "execution_point": "llm.request.header.assistant",
            "payload": {
                "assistant_content": "你好！我是架构小助",
                "finish_reason": "stop",
            },
        }
    }
    out_header = t.translate(header_ev)
    assert out_header == [], f"Expected [] to prevent duplicate append, but got {out_header}"


def test_non_streamed_call_still_emits_header_content_as_fallback() -> None:
    t = EventTranslator()

    # In a non-streamed or fallback scenario where no llm.stream.token was seen,
    # header assistant must still yield the text so content is never lost.
    header_ev = {
        "event": {
            "execution_point": "llm.request.header.assistant",
            "payload": {
                "assistant_content": "离线非流式回复内容",
                "finish_reason": "stop",
            },
        }
    }
    out_header = t.translate(header_ev)
    assert out_header[0]["type"] == "stream_chunk"
    assert out_header[0]["data"]["chunkType"] == "text"
    assert out_header[0]["data"]["content"] == "离线非流式回复内容"
