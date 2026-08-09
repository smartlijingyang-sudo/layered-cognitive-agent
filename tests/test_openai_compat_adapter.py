"""OpenAICompatAdapter 单元测试 —— AsyncMock 打桩，不发真实网络请求。"""

from __future__ import annotations

import importlib
import json
import os
import unittest
from dataclasses import dataclass
from typing import Any
from unittest import mock

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import TokenUsage
from lca.layer0_infra.llm_adapter.api_style import LLMApiStyle
from lca.layer0_infra.llm_adapter.openai_compat import OpenAICompatAdapter
from lca.layer0_infra.llm_adapter.openai_compat._chat_completions import to_openai_chat_tool_spec
from lca.layer0_infra.llm_adapter.openai_compat._responses import to_openai_responses_tool_spec

_HAS_OPENAI = importlib.util.find_spec("openai") is not None


@dataclass
class _FakeTool:
    name: str = "calculator"
    description: str = "calc"
    parameters: dict[str, Any] | None = None
    is_idempotent: bool = True
    default_timeout_s: int = 30

    def __post_init__(self) -> None:
        if self.parameters is None:
            self.parameters = {"type": "object", "properties": {}}


@dataclass
class _MockUsage:
    prompt_tokens: int = 5
    completion_tokens: int = 3
    input_tokens: int = 5
    output_tokens: int = 3


@dataclass
class _MockFunction:
    name: str = ""
    arguments: str = ""


@dataclass
class _MockToolCallDelta:
    index: int
    id: str = ""
    function: _MockFunction | None = None


@dataclass
class _MockDelta:
    content: str | None = None
    tool_calls: list[_MockToolCallDelta] | None = None
    reasoning_content: str | None = None


@dataclass
class _MockChoice:
    delta: _MockDelta


@dataclass
class _MockChatChunk:
    choices: list[_MockChoice]
    model: str = ""
    usage: _MockUsage | None = None


@dataclass
class _MockChatMessage:
    content: str | None = "hello"
    tool_calls: list[Any] | None = None


@dataclass
class _MockChatChoice:
    message: _MockChatMessage


@dataclass
class _MockChatResponse:
    choices: list[_MockChatChoice]
    model: str = "gpt-test"
    usage: _MockUsage | None = None


@unittest.skipUnless(_HAS_OPENAI, "openai SDK not installed")
class TestOpenAICompatAdapter(unittest.IsolatedAsyncioTestCase):
    def _patch_client(self) -> mock.Mock:
        client = mock.Mock()
        client.chat = mock.Mock()
        client.chat.completions = mock.Mock()
        client.responses = mock.Mock()
        return client

    async def test_default_uses_responses_strategy(self) -> None:
        client = self._patch_client()

        class _Resp:
            model = "gpt-resp"
            output_text = "hi"
            output = ()
            usage = _MockUsage()

        client.responses.create = mock.AsyncMock(return_value=_Resp())
        with mock.patch("openai.AsyncOpenAI", return_value=client):
            adapter = OpenAICompatAdapter(api_key="sk-test")
            result = await adapter.complete("prompt")
        self.assertEqual(result.text, "hi")
        client.responses.create.assert_awaited_once()
        client.chat.completions.create.assert_not_called()

    async def test_api_param_selects_chat_completions_strategy(self) -> None:
        client = self._patch_client()
        client.chat.completions.create = mock.AsyncMock(
            return_value=_MockChatResponse(
                choices=[_MockChatChoice(message=_MockChatMessage(content="chat"))]
            )
        )
        with mock.patch("openai.AsyncOpenAI", return_value=client):
            adapter = OpenAICompatAdapter(
                api_key="sk-test",
                api=LLMApiStyle.CHAT_COMPLETIONS,
            )
            result = await adapter.complete("prompt")
        self.assertEqual(result.text, "chat")
        client.chat.completions.create.assert_awaited_once()
        client.responses.create.assert_not_called()

    async def test_env_api_style_chat_completions(self) -> None:
        client = self._patch_client()
        client.chat.completions.create = mock.AsyncMock(
            return_value=_MockChatResponse(
                choices=[_MockChatChoice(message=_MockChatMessage(content="from env"))]
            )
        )
        with (
            mock.patch.dict(os.environ, {"LLM_API_STYLE": "chat_completions"}, clear=False),
            mock.patch("openai.AsyncOpenAI", return_value=client),
        ):
            adapter = OpenAICompatAdapter(api_key="sk-test")
            result = await adapter.complete("prompt")
        self.assertEqual(result.text, "from env")
        client.chat.completions.create.assert_awaited_once()

    async def test_explicit_api_overrides_env(self) -> None:
        client = self._patch_client()
        client.chat.completions.create = mock.AsyncMock(
            return_value=_MockChatResponse(
                choices=[_MockChatChoice(message=_MockChatMessage(content="chat"))]
            )
        )
        with (
            mock.patch.dict(os.environ, {"LLM_API_STYLE": "responses"}, clear=False),
            mock.patch("openai.AsyncOpenAI", return_value=client),
        ):
            adapter = OpenAICompatAdapter(
                api_key="sk-test",
                api=LLMApiStyle.CHAT_COMPLETIONS,
            )
            result = await adapter.complete("prompt")
        self.assertEqual(result.text, "chat")
        client.chat.completions.create.assert_awaited_once()

    def test_chat_tool_spec_nested(self) -> None:
        spec = to_openai_chat_tool_spec(_FakeTool())
        self.assertEqual(spec["type"], "function")
        self.assertIn("function", spec)
        self.assertEqual(spec["function"]["name"], "calculator")

    def test_responses_tool_spec_flat(self) -> None:
        spec = to_openai_responses_tool_spec(_FakeTool())
        self.assertEqual(spec["type"], "function")
        self.assertEqual(spec["name"], "calculator")
        self.assertNotIn("function", spec)

    async def test_chat_stream_completed_matches_complete(self) -> None:
        client = self._patch_client()
        complete_response = _MockChatResponse(
            choices=[_MockChatChoice(message=_MockChatMessage(content="Hello"))],
            usage=_MockUsage(),
        )
        client.chat.completions.create = mock.AsyncMock(return_value=complete_response)

        async def _stream(**kwargs: Any):
            if kwargs.get("stream"):

                async def _gen():
                    yield _MockChatChunk(choices=[_MockChoice(delta=_MockDelta(content="He"))])
                    yield _MockChatChunk(choices=[_MockChoice(delta=_MockDelta(content="llo"))])
                    yield _MockChatChunk(
                        choices=[],
                        model="gpt-test",
                        usage=_MockUsage(),
                    )

                return _gen()
            return complete_response

        client.chat.completions.create.side_effect = _stream

        with mock.patch("openai.AsyncOpenAI", return_value=client):
            adapter = OpenAICompatAdapter(
                api_key="sk-test",
                api=LLMApiStyle.CHAT_COMPLETIONS,
            )
            complete = await adapter.complete("prompt")
            events = [e async for e in adapter.stream("prompt")]

        deltas = [e for e in events if e.type == LLMStreamEventType.OUTPUT_TEXT_DELTA]
        completed = [e for e in events if e.type == LLMStreamEventType.COMPLETED]
        self.assertGreaterEqual(len(deltas), 1)
        self.assertEqual(len(completed), 1)
        self.assertIsNotNone(completed[0].response)
        assert completed[0].response is not None
        self.assertEqual(completed[0].response, complete)

    async def test_chat_stream_tool_call_encoding(self) -> None:
        client = self._patch_client()
        tc = mock.Mock()
        tc.id = "call_1"
        tc.function.name = "calculator"
        tc.function.arguments = '{"expression": "1+1"}'
        complete_response = _MockChatResponse(
            choices=[
                _MockChatChoice(
                    message=_MockChatMessage(content="", tool_calls=[tc]),
                )
            ],
            usage=_MockUsage(),
        )
        client.chat.completions.create = mock.AsyncMock(return_value=complete_response)

        async def _stream(**kwargs: Any):
            if kwargs.get("stream"):

                async def _gen():
                    yield _MockChatChunk(
                        choices=[
                            _MockChoice(
                                delta=_MockDelta(
                                    tool_calls=[
                                        _MockToolCallDelta(
                                            index=0,
                                            id="call_1",
                                            function=_MockFunction(
                                                name="calculator",
                                                arguments='{"expression":',
                                            ),
                                        )
                                    ]
                                )
                            )
                        ]
                    )
                    yield _MockChatChunk(
                        choices=[
                            _MockChoice(
                                delta=_MockDelta(
                                    tool_calls=[
                                        _MockToolCallDelta(
                                            index=0,
                                            function=_MockFunction(arguments='"1+1"}'),
                                        )
                                    ]
                                )
                            )
                        ]
                    )
                    yield _MockChatChunk(
                        choices=[],
                        model="gpt-test",
                        usage=_MockUsage(),
                    )

                return _gen()
            return complete_response

        client.chat.completions.create.side_effect = _stream

        with mock.patch("openai.AsyncOpenAI", return_value=client):
            adapter = OpenAICompatAdapter(
                api_key="sk-test",
                api=LLMApiStyle.CHAT_COMPLETIONS,
            )
            complete = await adapter.complete("prompt", tools=[_FakeTool()])
            events = [e async for e in adapter.stream("prompt", tools=[_FakeTool()])]

        fn_deltas = [
            e for e in events if e.type == LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA
        ]
        completed = next(e for e in events if e.type == LLMStreamEventType.COMPLETED)
        self.assertGreaterEqual(len(fn_deltas), 1)
        assert completed.response is not None
        self.assertEqual(completed.response.text, complete.text)
        payload = json.loads(completed.response.text)
        self.assertEqual(payload["action_type"], "use_tool")
        self.assertEqual(payload["tool_name"], "calculator")

    async def test_chat_stream_reasoning_content_field(self) -> None:
        client = self._patch_client()
        complete_response = _MockChatResponse(
            choices=[_MockChatChoice(message=_MockChatMessage(content='{"a":1}'))],
            usage=_MockUsage(),
        )

        async def _stream(**kwargs: Any):
            if kwargs.get("stream"):

                async def _gen():
                    yield _MockChatChunk(
                        choices=[_MockChoice(delta=_MockDelta(reasoning_content="先分析问题"))]
                    )
                    yield _MockChatChunk(choices=[_MockChoice(delta=_MockDelta(content='{"a":1}'))])
                    yield _MockChatChunk(choices=[], model="gpt-test", usage=_MockUsage())

                return _gen()
            return complete_response

        client.chat.completions.create.side_effect = _stream
        with mock.patch("openai.AsyncOpenAI", return_value=client):
            adapter = OpenAICompatAdapter(
                api_key="sk-test",
                api=LLMApiStyle.CHAT_COMPLETIONS,
            )
            events = [e async for e in adapter.stream("prompt")]

        reasoning = [e for e in events if e.type == LLMStreamEventType.REASONING_TEXT_DELTA]
        content = [e for e in events if e.type == LLMStreamEventType.OUTPUT_TEXT_DELTA]
        self.assertEqual("".join(e.text for e in reasoning), "先分析问题")
        self.assertEqual("".join(e.text for e in content), '{"a":1}')

    async def test_chat_stream_think_tags_split_to_reasoning(self) -> None:
        client = self._patch_client()
        complete_response = _MockChatResponse(
            choices=[_MockChatChoice(message=_MockChatMessage(content="answer"))],
            usage=_MockUsage(),
        )

        async def _stream(**kwargs: Any):
            if kwargs.get("stream"):

                async def _gen():
                    yield _MockChatChunk(
                        choices=[_MockChoice(delta=_MockDelta(content="<think>逐步"))]
                    )
                    yield _MockChatChunk(
                        choices=[_MockChoice(delta=_MockDelta(content="推理</think>answer"))]
                    )
                    yield _MockChatChunk(choices=[], model="gpt-test", usage=_MockUsage())

                return _gen()
            return complete_response

        client.chat.completions.create.side_effect = _stream
        with mock.patch("openai.AsyncOpenAI", return_value=client):
            adapter = OpenAICompatAdapter(
                api_key="sk-test",
                api=LLMApiStyle.CHAT_COMPLETIONS,
            )
            events = [e async for e in adapter.stream("prompt")]

        reasoning = "".join(
            e.text for e in events if e.type == LLMStreamEventType.REASONING_TEXT_DELTA
        )
        content = "".join(e.text for e in events if e.type == LLMStreamEventType.OUTPUT_TEXT_DELTA)
        completed = next(e for e in events if e.type == LLMStreamEventType.COMPLETED)
        self.assertEqual(reasoning, "逐步推理")
        self.assertEqual(content, "answer")
        assert completed.response is not None
        self.assertEqual(completed.response.text, "answer")

    async def test_responses_stream_reasoning_text_delta(self) -> None:
        client = self._patch_client()

        class _Resp:
            model = "gpt-resp"
            output_text = "final"
            output = ()
            usage = _MockUsage(input_tokens=4, output_tokens=2)

        @dataclass
        class _ReasoningDelta:
            type: str = "response.reasoning_text.delta"
            delta: str = "思考中"

        @dataclass
        class _TextDelta:
            type: str = "response.output_text.delta"
            delta: str = "final"

        @dataclass
        class _Completed:
            type: str = "response.completed"
            response: _Resp = None  # type: ignore[assignment]

        async def _stream(**kwargs: Any):
            if kwargs.get("stream"):

                async def _gen():
                    yield _ReasoningDelta()
                    yield _TextDelta()
                    done = _Completed()
                    done.response = _Resp()
                    yield done

                return _gen()
            return _Resp()

        client.responses.create.side_effect = _stream
        with mock.patch("openai.AsyncOpenAI", return_value=client):
            adapter = OpenAICompatAdapter(api_key="sk-test", api=LLMApiStyle.RESPONSES)
            events = [e async for e in adapter.stream("prompt")]

        reasoning = [e for e in events if e.type == LLMStreamEventType.REASONING_TEXT_DELTA]
        self.assertEqual(len(reasoning), 1)
        self.assertEqual(reasoning[0].text, "思考中")

    async def test_chat_request_includes_qwen_params_and_parallel_tools(self) -> None:
        client = self._patch_client()
        client.chat.completions.create = mock.AsyncMock(
            return_value=_MockChatResponse(
                choices=[_MockChatChoice(message=_MockChatMessage(content="ok"))]
            )
        )
        with mock.patch("openai.AsyncOpenAI", return_value=client):
            adapter = OpenAICompatAdapter(
                api_key="sk-test",
                model="qwen3.7-plus",
                api=LLMApiStyle.CHAT_COMPLETIONS,
            )
            await adapter.complete("prompt", tools=[_FakeTool()])
        kwargs = client.chat.completions.create.await_args.kwargs
        self.assertTrue(kwargs["parallel_tool_calls"])
        self.assertIn("top_p", kwargs)
        self.assertEqual(kwargs["extra_body"]["enable_thinking"], True)
        self.assertEqual(kwargs["extra_body"]["top_k"], 20)
        self.assertEqual(kwargs["tools"][0]["function"]["name"], "calculator")

    async def test_responses_usage_mapping(self) -> None:
        client = self._patch_client()

        class _Resp:
            model = "gpt-resp"
            output_text = "x"
            output = ()
            usage = _MockUsage(input_tokens=11, output_tokens=7)

        client.responses.create = mock.AsyncMock(return_value=_Resp())
        with mock.patch("openai.AsyncOpenAI", return_value=client):
            adapter = OpenAICompatAdapter(api_key="sk-test", api=LLMApiStyle.RESPONSES)
            result = await adapter.complete("prompt")
        self.assertEqual(result.usage, TokenUsage(prompt_tokens=11, completion_tokens=7))

    async def test_responses_stream_completed_matches_complete(self) -> None:
        client = self._patch_client()

        class _Resp:
            model = "gpt-resp"
            output_text = "streamed"
            output = ()
            usage = _MockUsage(input_tokens=4, output_tokens=2)

        @dataclass
        class _TextDelta:
            type: str = "response.output_text.delta"
            delta: str = "streamed"

        @dataclass
        class _Completed:
            type: str = "response.completed"
            response: _Resp = None  # type: ignore[assignment]

        async def _stream(**kwargs: Any):
            if kwargs.get("stream"):

                async def _gen():
                    yield _TextDelta()
                    done = _Completed()
                    done.response = _Resp()
                    yield done

                return _gen()
            return _Resp()

        client.responses.create.side_effect = _stream

        with mock.patch("openai.AsyncOpenAI", return_value=client):
            adapter = OpenAICompatAdapter(api_key="sk-test", api=LLMApiStyle.RESPONSES)
            complete = await adapter.complete("prompt")
            events = [e async for e in adapter.stream("prompt")]

        completed = next(e for e in events if e.type == LLMStreamEventType.COMPLETED)
        assert completed.response is not None
        self.assertEqual(completed.response, complete)


if __name__ == "__main__":
    unittest.main()
