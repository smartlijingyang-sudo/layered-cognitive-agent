"""PromptReasoner 流式路径 —— n=1 时 stream 拼接与 complete 逐字符一致（ADR-0041）。"""

from __future__ import annotations

import unittest
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.infrastructure.search.constants import WEB_SEARCH_TOOL
from lca.layer1_cognitive.brain.reasoner import PromptReasoner


def _empty_manifest() -> ToolPermissionManifest:
    return ToolPermissionManifest(allowed_tools=[])


def _profile() -> RoleProfile:
    return RoleProfile(
        role="agent",
        goal="test",
        backstory="",
        tool_permission_manifest=_empty_manifest(),
    )


def _state(*, step: int = 3) -> AgentState:
    return AgentState(trace_id="t", task="task", budget=Budget(), step=step)


def _state_after_web_search(*, step: int = 1) -> AgentState:
    state = AgentState(trace_id="t", task="今天有什么新闻", budget=Budget(), step=step)
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


class _DualPathLLM:
    """complete 与 stream 双路径，用于断言拼接不变式。"""

    def __init__(self, text: str) -> None:
        self.text = text
        self.stream_steps: list[int] = []

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return LLMResponse(text=self.text)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        step = kwargs.get("step")
        if isinstance(step, int):
            self.stream_steps.append(step)
        chunk_size = max(1, len(self.text) // 3) if self.text else 0
        pos = 0
        while pos < len(self.text):
            piece = self.text[pos : pos + chunk_size]
            pos += chunk_size
            yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=piece)
        yield LLMStreamEvent(
            type=LLMStreamEventType.COMPLETED,
            response=LLMResponse(text=self.text),
        )


class _ReasoningOnlyStreamLLM:
    """Simulates Qwen thinking streams: CoT in reasoning channel, empty content."""

    def __init__(self, text: str) -> None:
        self.text = text

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return LLMResponse(text="")

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        yield LLMStreamEvent(type=LLMStreamEventType.REASONING_TEXT_DELTA, text=self.text)
        yield LLMStreamEvent(
            type=LLMStreamEventType.COMPLETED,
            response=LLMResponse(text=""),
        )


class _EmptyStreamCompleteFallbackLLM:
    """Stream yields no usable text; complete() carries the decision JSON."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.complete_calls = 0

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        self.complete_calls += 1
        return LLMResponse(text=self.text)

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        # Yield COMPLETED with response=None so the code falls through
        # to the complete() fallback path.
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=None)


class TestReasonerStreamPath(unittest.IsolatedAsyncioTestCase):
    async def test_empty_stream_falls_back_to_complete(self) -> None:
        expected = '{"action_type":"respond","response_text":"news summary","confidence":0.9}'
        llm = _EmptyStreamCompleteFallbackLLM(expected)
        reasoner = PromptReasoner(
            llm,
            _profile(),
            "",
            templates={"react_prompt": "TASK: {task}\n{context}"},
        )
        result = await reasoner.generate_thoughts(_state())
        self.assertEqual(result.text, expected)
        self.assertEqual(llm.complete_calls, 1)

    async def test_empty_stream_retries_complete_until_text(self) -> None:
        expected = '{"action_type":"respond","response_text":"ok","confidence":0.9}'

        class _RetryCompleteLLM:
            def __init__(self) -> None:
                self.complete_calls = 0

            async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
                self.complete_calls += 1
                if self.complete_calls == 1:
                    return LLMResponse(text="")
                return LLMResponse(text=expected)

            async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
                # Yield COMPLETED with response=None so the code falls through
                # to the complete() fallback path.
                yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=None)

        llm = _RetryCompleteLLM()
        reasoner = PromptReasoner(
            llm,
            _profile(),
            "",
            templates={"react_prompt": "{task}"},
        )
        result = await reasoner.generate_thoughts(_state())
        self.assertEqual(result.text, expected)
        self.assertEqual(llm.complete_calls, 2)

    async def test_n1_uses_stream_and_matches_complete_text(self) -> None:
        expected = '{"action_type":"respond","response_text":"hello","confidence":1.0}'
        llm = _DualPathLLM(expected)
        reasoner = PromptReasoner(
            llm,
            _profile(),
            "",
            templates={"react_prompt": "TASK: {task}\n{context}"},
        )
        result = await reasoner.generate_thoughts(_state(step=7))
        self.assertEqual(result.text, expected)
        self.assertEqual(llm.stream_steps, [7])

    async def test_reasoning_only_stream_is_not_used_for_decision(self) -> None:
        reasoning_json = (
            '{"action_type":"use_tool","tool_name":"web_search",'
            '"arguments":{"query":"today news"},"rationale":"x","confidence":0.9}'
        )
        llm = _ReasoningOnlyStreamLLM(reasoning_json)
        reasoner = PromptReasoner(
            llm,
            _profile(),
            "",
            templates={"react_prompt": "TASK: {task}\n{context}"},
        )
        result = await reasoner.generate_thoughts(_state())
        self.assertEqual(result.text, "")

    async def test_post_search_uses_stream(self) -> None:
        expected = '{"action_type":"respond","response_text":"news","confidence":0.9}'
        calls: list[str] = []

        class _PostSearchLLM:
            async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
                calls.append("complete")
                return LLMResponse(text="")

            async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
                calls.append("stream")
                yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=expected)
                yield LLMStreamEvent(
                    type=LLMStreamEventType.COMPLETED,
                    response=LLMResponse(text=expected),
                )

        llm = _PostSearchLLM()
        reasoner = PromptReasoner(
            llm,
            _profile(),
            "",
            templates={"react_prompt": "TASK: {task}\n{context}"},
        )
        result = await reasoner.generate_thoughts(_state_after_web_search())
        self.assertEqual(result.text, expected)
        self.assertEqual(calls, ["stream"])


if __name__ == "__main__":
    unittest.main()
