"""PromptReasoner 流式路径 —— n=1 时 stream 拼接与 complete 逐字符一致（ADR-0041）。"""

from __future__ import annotations

import unittest
from collections.abc import AsyncIterator
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
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


class TestReasonerStreamPath(unittest.IsolatedAsyncioTestCase):
    async def test_n1_uses_stream_and_matches_complete_text(self) -> None:
        expected = '{"action_type":"respond","response_text":"hello","confidence":1.0}'
        llm = _DualPathLLM(expected)
        reasoner = PromptReasoner(
            llm,
            _profile(),
            "",
            templates={"react_prompt": "TASK: {task}\n{context}"},
        )
        thoughts = await reasoner.generate_thoughts(_state(step=7))
        self.assertEqual(thoughts, [expected])
        self.assertEqual(llm.stream_steps, [7])

    async def test_n_gt_1_still_uses_complete(self) -> None:
        calls: list[str] = []

        class CompleteOnlyLLM:
            async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
                calls.append("complete")
                return LLMResponse(text="a")

            async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
                calls.append("stream")
                yield LLMStreamEvent(
                    type=LLMStreamEventType.COMPLETED, response=LLMResponse(text="a")
                )

        llm = CompleteOnlyLLM()
        reasoner = PromptReasoner(
            llm,
            _profile(),
            "",
            templates={"react_prompt": "{task}"},
        )
        result = await reasoner.generate_thoughts(_state(), n=2)
        self.assertEqual(result, ["a", "a"])
        self.assertEqual(calls, ["complete", "complete"])


if __name__ == "__main__":
    unittest.main()
