"""Tests for LLM stream channel classification (ADR-0051 Phase 2)."""

from __future__ import annotations

from lca.contracts.atoms.enums import StreamChannel
from lca.layer0_infra.observability.stream_channel import classify_output_channel


class TestStreamChannel:
    def test_empty_is_decision(self) -> None:
        assert classify_output_channel("") == StreamChannel.DECISION.value

    def test_json_tool_decision(self) -> None:
        text = '{"action_type": "use_tool", "tool_name": "sandbox_execute"}'
        assert classify_output_channel(text) == StreamChannel.DECISION.value

    def test_respond_json_is_answer(self) -> None:
        text = '{"action_type": "respond", "response_text": "你好"}'
        assert classify_output_channel(text) == StreamChannel.ANSWER.value

    def test_plain_prose_is_answer(self) -> None:
        assert classify_output_channel("这是用户可见的回答") == StreamChannel.ANSWER.value

    def test_codeblock_prefix_is_decision(self) -> None:
        assert classify_output_channel("```json\n{") == StreamChannel.DECISION.value
