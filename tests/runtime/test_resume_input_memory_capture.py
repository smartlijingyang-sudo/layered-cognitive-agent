"""PR-8（ADR-0246）：暂停恢复路径补跑记忆捕获。"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import ActionType, MemoryLayer
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision, Observation, Turn
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.session.resume.input import ResumeInput
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.runtime.support.resume_memory import capture_resume_memory


def _resume_input(answer: str) -> ResumeInput:
    observation = Observation(
        observation_id="obs_1",
        success=True,
        payload=answer,
        extra={"source": "human_answer", "tool_name": "askUserQuestion"},
    )
    decision = Decision(
        decision_id="dec_1",
        action_type=ActionType.ASK_HUMAN,
        rationale="Human-in-the-loop answer received.",
        confidence=1.0,
    )
    return ResumeInput(input_value=answer, turn=Turn(decision=decision, observation=observation))


class _JsonAdapter:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls = 0

    async def complete(self, prompt: str, **kwargs: object) -> LLMResponse:
        self.calls += 1
        return LLMResponse(text=self._text, model="stub")


def _state() -> AgentState:
    return AgentState(trace_id="trace_t", task="我是架构师", budget=Budget())


@pytest.mark.asyncio
async def test_resume_capture_persists_identity(tmp_path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    adapter = _JsonAdapter(
        '[{"category": "identity", "content": "用户身份：架构师", '
        '"confidence": 1.0, "dedupe_key": "identity:architect"}]'
    )
    resume_input = _resume_input("我是架构师")

    written = await capture_resume_memory(memory, adapter, resume_input, _state())

    assert written is True
    assert adapter.calls == 1
    semantic = memory.query(MemoryLayer.SEMANTIC)
    assert len(semantic) == 1
    assert semantic[0].content == "用户身份：架构师"
    assert semantic[0].dedupe_key == "identity:architect"


@pytest.mark.asyncio
async def test_resume_capture_fast_path_no_llm(tmp_path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    adapter = _JsonAdapter("[]")
    resume_input = _resume_input("好的，谢谢")

    written = await capture_resume_memory(memory, adapter, resume_input, _state())

    assert written is False
    assert adapter.calls == 0
    assert memory.query(MemoryLayer.SEMANTIC) == []
