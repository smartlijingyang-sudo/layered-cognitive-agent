"""Anthropic Messages 策略：Coding Plan /apps/anthropic 不能走 /chat/completions。"""

from __future__ import annotations

import json
import os
import unittest
from dataclasses import dataclass
from typing import Any
from unittest import mock

from lca.contracts.atoms.enums import FinishReason, LLMStreamEventType
from lca.layer0_infra.llm_adapter.api_style import LLMApiStyle
from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter
from lca.layer0_infra.llm_adapter.settings import clear_llm_settings_cache


@dataclass
class _FakeTool:
    name: str = "run_command"
    description: str = "run a shell command"
    parameters: dict[str, Any] | None = None
    is_idempotent: bool = True
    default_timeout_s: int = 30

    def __post_init__(self) -> None:
        if self.parameters is None:
            self.parameters = {
                "type": "object",
                "properties": {"command": {"type": "string"}},
            }


def _sse(event_type: str, payload: dict[str, Any]) -> list[str]:
    body = dict(payload)
    body.setdefault("type", event_type)
    return [f"event: {event_type}", f"data: {json.dumps(body, ensure_ascii=False)}", ""]


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeStreamResponse:
    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def __aenter__(self) -> _FakeStreamResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


class _FakeAsyncClient:
    last: _FakeAsyncClient | None = None
    next_payload: dict[str, Any] | None = None
    next_stream_lines: list[str] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.posts: list[tuple[str, dict[str, Any], dict[str, str]]] = []
        self.payload = _FakeAsyncClient.next_payload or {
            "id": "msg_1",
            "model": "qwen3.7-plus",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "pong"}],
            "usage": {"input_tokens": 3, "output_tokens": 1},
        }
        self.stream_lines = list(
            _FakeAsyncClient.next_stream_lines
            or [
                *_sse(
                    "content_block_delta",
                    {"index": 0, "delta": {"type": "text_delta", "text": "pong"}},
                ),
                *_sse("message_stop", {}),
            ]
        )
        _FakeAsyncClient.last = self

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _FakeResponse:
        self.posts.append((url, json or {}, headers or {}))
        return _FakeResponse(self.payload)

    def stream(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _FakeStreamResponse:
        del method
        self.posts.append((url, json or {}, headers or {}))
        return _FakeStreamResponse(self.stream_lines)


class TestAnthropicMessagesAdapter(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        clear_llm_settings_cache()
        _FakeAsyncClient.last = None
        _FakeAsyncClient.next_payload = None
        _FakeAsyncClient.next_stream_lines = None
        for key in ("LLM_API_STYLE", "LLM_BASE_URL"):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        clear_llm_settings_cache()
        _FakeAsyncClient.next_payload = None
        _FakeAsyncClient.next_stream_lines = None
        for key in ("LLM_API_STYLE", "LLM_BASE_URL"):
            os.environ.pop(key, None)

    async def test_coding_plan_base_url_uses_messages_not_openai(self) -> None:
        with (
            mock.patch("openai.AsyncOpenAI") as openai_cls,
            mock.patch("httpx.AsyncClient", _FakeAsyncClient),
        ):
            adapter = OpenAICompatAdapter(
                api_key="sk-sp-test",
                base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic",
                model="qwen3.7-plus",
            )
            result = await adapter.complete("ping")
        openai_cls.assert_not_called()
        self.assertEqual(result.text, "pong")
        posted = _FakeAsyncClient.last
        assert posted is not None
        url, body, headers = posted.posts[0]
        self.assertEqual(
            url,
            "https://coding.dashscope.aliyuncs.com/apps/anthropic/v1/messages",
        )
        self.assertEqual(body["model"], "qwen3.7-plus")
        self.assertEqual(body["messages"], [{"role": "user", "content": "ping"}])
        self.assertIn("max_tokens", body)
        self.assertEqual(headers["x-api-key"], "sk-sp-test")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")

    async def test_env_api_style_anthropic(self) -> None:
        with (
            mock.patch.dict(os.environ, {"LLM_API_STYLE": "anthropic"}, clear=False),
            mock.patch("openai.AsyncOpenAI") as openai_cls,
            mock.patch("httpx.AsyncClient", _FakeAsyncClient),
        ):
            adapter = OpenAICompatAdapter(
                api_key="sk-test",
                base_url="https://example.invalid",
            )
            result = await adapter.complete("ping")
        openai_cls.assert_not_called()
        self.assertEqual(result.text, "pong")
        posted = _FakeAsyncClient.last
        assert posted is not None
        self.assertTrue(posted.posts[0][0].endswith("/v1/messages"))

    async def test_explicit_chat_completions_overrides_coding_url(self) -> None:
        client = mock.Mock()
        client.chat = mock.Mock()
        client.chat.completions = mock.Mock()
        client.responses = mock.Mock()
        client.chat.completions.create = mock.AsyncMock(
            return_value=mock.Mock(
                choices=[mock.Mock(message=mock.Mock(content="chat", tool_calls=None))],
                model="qwen3.7-plus",
                usage=None,
            )
        )
        with mock.patch("openai.AsyncOpenAI", return_value=client):
            adapter = OpenAICompatAdapter(
                api_key="sk-test",
                base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic",
                api=LLMApiStyle.CHAT_COMPLETIONS,
            )
            result = await adapter.complete("ping")
        self.assertEqual(result.text, "chat")
        client.chat.completions.create.assert_awaited_once()

    async def test_history_is_native_tool_use_not_prompt_prose(self) -> None:
        history = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "toolu_1", "name": "run_command", "arguments": {"command": "ls"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "toolu_1",
                "name": "run_command",
                "content": "a.txt",
            },
        ]
        with mock.patch("httpx.AsyncClient", _FakeAsyncClient):
            adapter = OpenAICompatAdapter(
                api_key="sk-sp-test",
                base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic",
                api=LLMApiStyle.ANTHROPIC,
            )
            await adapter.complete("continue", tools=[_FakeTool()], history=history)
        posted = _FakeAsyncClient.last
        assert posted is not None
        body = posted.posts[0][1]
        messages = body["messages"]
        self.assertEqual(messages[0], {"role": "user", "content": "continue"})
        self.assertEqual(messages[1]["content"][0]["type"], "tool_use")
        self.assertEqual(messages[1]["content"][0]["id"], "toolu_1")
        self.assertEqual(messages[2]["content"][0]["type"], "tool_result")
        self.assertEqual(messages[2]["content"][0]["tool_use_id"], "toolu_1")

    async def test_complete_maps_tool_use(self) -> None:
        _FakeAsyncClient.next_payload = {
            "model": "qwen3.7-plus",
            "stop_reason": "tool_use",
            "content": [
                {"type": "text", "text": ""},
                {
                    "type": "tool_use",
                    "id": "call_1",
                    "name": "run_command",
                    "input": {"command": "echo hi"},
                },
            ],
            "usage": {"input_tokens": 10, "output_tokens": 4},
        }
        with mock.patch("httpx.AsyncClient", _FakeAsyncClient):
            adapter = OpenAICompatAdapter(
                api_key="sk-sp-test",
                base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic",
                api=LLMApiStyle.ANTHROPIC,
            )
            result = await adapter.complete("do it", tools=[_FakeTool()])
        posted = _FakeAsyncClient.last
        assert posted is not None
        self.assertEqual(result.finish_reason, FinishReason.TOOL_CALLS.value)
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0].name, "run_command")
        self.assertEqual(result.tool_calls[0].arguments["command"], "echo hi")
        body = posted.posts[0][1]
        self.assertEqual(body["tools"][0]["name"], "run_command")
        self.assertEqual(body["tools"][0]["input_schema"]["type"], "object")
        self.assertNotIn("extra_body", body)

    async def test_base_url_already_ending_v1_does_not_double(self) -> None:
        with mock.patch("httpx.AsyncClient", _FakeAsyncClient):
            adapter = OpenAICompatAdapter(
                api_key="sk-sp-test",
                base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic/v1",
                api=LLMApiStyle.ANTHROPIC,
            )
            await adapter.complete("ping")
        posted = _FakeAsyncClient.last
        assert posted is not None
        self.assertEqual(
            posted.posts[0][0],
            "https://coding.dashscope.aliyuncs.com/apps/anthropic/v1/messages",
        )

    async def test_complete_thinking_block_is_not_response_text(self) -> None:
        _FakeAsyncClient.next_payload = {
            "model": "qwen3.7-plus",
            "stop_reason": "end_turn",
            "content": [
                {"type": "thinking", "thinking": "先拆问题"},
                {"type": "text", "text": "hello"},
            ],
            "usage": {"input_tokens": 4, "output_tokens": 8},
        }
        with mock.patch("httpx.AsyncClient", _FakeAsyncClient):
            adapter = OpenAICompatAdapter(
                api_key="sk-sp-test",
                base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic",
                api=LLMApiStyle.ANTHROPIC,
            )
            result = await adapter.complete("ping")
        self.assertEqual(result.text, "hello")

    async def test_stream_emits_reasoning_then_text_like_chat(self) -> None:
        _FakeAsyncClient.next_stream_lines = [
            *_sse(
                "content_block_start",
                {"index": 0, "content_block": {"type": "thinking", "thinking": ""}},
            ),
            *_sse(
                "content_block_delta",
                {"index": 0, "delta": {"type": "thinking_delta", "thinking": "先分析"}},
            ),
            *_sse(
                "content_block_start",
                {"index": 1, "content_block": {"type": "text", "text": ""}},
            ),
            *_sse(
                "content_block_delta",
                {"index": 1, "delta": {"type": "text_delta", "text": "答案"}},
            ),
            *_sse(
                "message_delta",
                {
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {"output_tokens": 6},
                },
            ),
            *_sse("message_stop", {}),
        ]
        with mock.patch("httpx.AsyncClient", _FakeAsyncClient):
            adapter = OpenAICompatAdapter(
                api_key="sk-sp-test",
                base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic",
                api=LLMApiStyle.ANTHROPIC,
            )
            events = [e async for e in adapter.stream("ping")]
        posted = _FakeAsyncClient.last
        assert posted is not None
        body = posted.posts[0][1]
        self.assertTrue(body["stream"])
        self.assertTrue(body["enable_thinking"])
        self.assertNotIn("extra_body", body)
        reasoning = [e for e in events if e.type == LLMStreamEventType.REASONING_TEXT_DELTA]
        text = [e for e in events if e.type == LLMStreamEventType.OUTPUT_TEXT_DELTA]
        completed = next(e for e in events if e.type == LLMStreamEventType.COMPLETED)
        self.assertEqual("".join(e.text for e in reasoning), "先分析")
        self.assertEqual("".join(e.text for e in text), "答案")
        assert completed.response is not None
        self.assertEqual(completed.response.text, "答案")

    async def test_stream_think_tags_in_text_split_like_chat(self) -> None:
        _FakeAsyncClient.next_stream_lines = [
            *_sse(
                "content_block_delta",
                {"index": 0, "delta": {"type": "text_delta", "text": "<think>逐步"}},
            ),
            *_sse(
                "content_block_delta",
                {"index": 0, "delta": {"type": "text_delta", "text": "推理</think>answer"}},
            ),
            *_sse("message_stop", {}),
        ]
        with mock.patch("httpx.AsyncClient", _FakeAsyncClient):
            adapter = OpenAICompatAdapter(
                api_key="sk-sp-test",
                base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic",
                api=LLMApiStyle.ANTHROPIC,
            )
            events = [e async for e in adapter.stream("ping")]
        reasoning = "".join(
            e.text for e in events if e.type == LLMStreamEventType.REASONING_TEXT_DELTA
        )
        content = "".join(e.text for e in events if e.type == LLMStreamEventType.OUTPUT_TEXT_DELTA)
        completed = next(e for e in events if e.type == LLMStreamEventType.COMPLETED)
        self.assertEqual(reasoning, "逐步推理")
        self.assertEqual(content, "answer")
        assert completed.response is not None
        self.assertEqual(completed.response.text, "answer")

    async def test_stream_tool_use_json_deltas(self) -> None:
        _FakeAsyncClient.next_stream_lines = [
            *_sse(
                "content_block_start",
                {
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "run_command",
                        "input": {},
                    },
                },
            ),
            *_sse(
                "content_block_delta",
                {"index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"command":'}},
            ),
            *_sse(
                "content_block_delta",
                {"index": 0, "delta": {"type": "input_json_delta", "partial_json": '"echo hi"}'}},
            ),
            *_sse(
                "message_delta",
                {"delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 4}},
            ),
            *_sse("message_stop", {}),
        ]
        with mock.patch("httpx.AsyncClient", _FakeAsyncClient):
            adapter = OpenAICompatAdapter(
                api_key="sk-sp-test",
                base_url="https://coding.dashscope.aliyuncs.com/apps/anthropic",
                api=LLMApiStyle.ANTHROPIC,
            )
            events = [e async for e in adapter.stream("do it", tools=[_FakeTool()])]
        fn_deltas = [
            e for e in events if e.type == LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA
        ]
        completed = next(e for e in events if e.type == LLMStreamEventType.COMPLETED)
        self.assertGreaterEqual(len(fn_deltas), 1)
        self.assertEqual(fn_deltas[0].tool_name, "run_command")
        self.assertEqual(fn_deltas[0].tool_call_id, "call_1")
        assert completed.response is not None
        self.assertEqual(completed.response.finish_reason, FinishReason.TOOL_CALLS.value)
        self.assertEqual(len(completed.response.tool_calls), 1)
        self.assertEqual(completed.response.tool_calls[0].name, "run_command")
        self.assertEqual(completed.response.tool_calls[0].arguments["command"], "echo hi")


if __name__ == "__main__":
    unittest.main()
