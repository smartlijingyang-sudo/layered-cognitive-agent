"""Tests for LobeHub-aligned llm_turn (one LLM call per step)."""

from __future__ import annotations

import unittest
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent, NativeToolCall
from lca.contracts.models.core.state import AgentState, Budget
from lca.infrastructure.search.constants import WEB_SEARCH_TOOL
from lca.layer1_cognitive.brain.llm_turn import execute_llm_turn
from lca.plugins.providers.decision_classifier import DefaultDecisionClassifier


def _state_after_web_search() -> AgentState:
    state = AgentState(trace_id="t", task="今天有什么新闻", budget=Budget(), step=1)
    state.history.append(
        Turn(
            decision=Decision(
                decision_id="dec0",
                action_type="use_tool",
                rationale="search",
                confidence=0.9,
                tool_calls=[
                    ToolCall(call_id="c1", tool_name=WEB_SEARCH_TOOL, arguments={"query": "news"})
                ],
            ),
            observation=Observation(
                observation_id="obs1",
                success=True,
                payload={"text": "summary", "query": "news", "provider": "tavily"},
            ),
        )
    )
    return state


class _TextOnlyStreamLLM:
    """Stream text-only response; complete must not be called for forced tools."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.complete_calls = 0

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        self.complete_calls += 1
        return LLMResponse(text=self.text)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        chunk_size = max(1, len(self.text) // 2) if self.text else 0
        pos = 0
        while pos < len(self.text):
            piece = self.text[pos : pos + chunk_size]
            pos += chunk_size
            yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=piece)
        yield LLMStreamEvent(
            type=LLMStreamEventType.COMPLETED,
            response=LLMResponse(text=self.text),
        )


class _ToolCallStreamLLM:
    def __init__(self) -> None:
        self.complete_calls = 0

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        self.complete_calls += 1
        return LLMResponse(
            text="",
            tool_calls=[
                NativeToolCall(call_id="c1", name="web_search", arguments={"query": "news"})
            ],
        )

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        response = LLMResponse(
            text="",
            tool_calls=[
                NativeToolCall(call_id="c1", name="web_search", arguments={"query": "news"})
            ],
        )
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)


class TestLlmTurn(unittest.IsolatedAsyncioTestCase):
    async def test_text_only_single_stream_no_forced_complete(self) -> None:
        llm = _TextOnlyStreamLLM("我可以帮您完成多种任务")
        state = AgentState(trace_id="t", task="你能做什么", budget=Budget(), step=0)
        result = await execute_llm_turn(llm, [], "prompt", step=0, state=state, task=state.task)
        self.assertEqual(result.text, "我可以帮您完成多种任务")
        self.assertFalse(result.tool_calls)
        self.assertEqual(llm.complete_calls, 0)

    async def test_text_only_builds_respond_decision(self) -> None:
        response = LLMResponse(text="hello")
        decision = DefaultDecisionClassifier().classify(response)
        self.assertEqual(decision.action_type, "respond")
        self.assertFalse(response.tool_calls)

    async def test_tool_calls_builds_use_tool(self) -> None:
        response = LLMResponse(
            text="",
            tool_calls=[NativeToolCall(call_id="c1", name="web_search", arguments={"query": "x"})],
        )
        decision = DefaultDecisionClassifier().classify(response)
        self.assertEqual(decision.action_type, "use_tool")
        self.assertTrue(response.tool_calls)

    async def test_post_search_uses_stream(self) -> None:
        calls: list[str] = []

        class _PostSearchLLM:
            async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
                calls.append("complete")
                return LLMResponse(text="")

            async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
                calls.append("stream")
                assert kwargs.get("tool_choice") == "none"
                yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text="news")
                yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=" summary")
                yield LLMStreamEvent(
                    type=LLMStreamEventType.COMPLETED,
                    response=LLMResponse(text="news summary"),
                )

        llm = _PostSearchLLM()
        state = _state_after_web_search()
        result = await execute_llm_turn(llm, [], "prompt", step=1, state=state, task=state.task)
        self.assertEqual(result.text, "news summary")
        self.assertEqual(calls, ["stream"])

    async def test_tool_call_from_single_stream(self) -> None:
        llm = _ToolCallStreamLLM()
        state = AgentState(trace_id="t", task="news", budget=Budget(), step=0)
        result = await execute_llm_turn(llm, [], "prompt", step=0, state=state, task=state.task)
        self.assertTrue(result.tool_calls)
        self.assertEqual(llm.complete_calls, 0)


if __name__ == "__main__":
    unittest.main()
