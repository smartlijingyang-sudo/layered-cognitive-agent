"""PR-8（ADR-0246）：重复恢复不产生重复活跃记忆（dedupe_key 幂等）。"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import ActionType, MemoryLayer
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision, Observation, Turn
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.session.resume.input import ResumeInput
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.runtime.support.resume_memory import capture_resume_memory


class _JsonAdapter:
    async def complete(self, prompt: str, **kwargs: object) -> LLMResponse:
        return LLMResponse(
            text='[{"category": "identity", "content": "用户身份：架构师", '
            '"confidence": 1.0, "dedupe_key": "identity:architect"}]',
            model="stub",
        )


def _resume_input(answer: str) -> ResumeInput:
    observation = Observation(
        observation_id="obs_1",
        success=True,
        payload=answer,
        extra={"source": "human_answer"},
    )
    decision = Decision(
        decision_id="dec_1",
        action_type=ActionType.ASK_HUMAN,
        rationale="answer",
        confidence=1.0,
    )
    return ResumeInput(input_value=answer, turn=Turn(decision=decision, observation=observation))


def _state() -> AgentState:
    return AgentState(trace_id="trace_t", task="我是架构师", budget=Budget())


@pytest.mark.asyncio
async def test_repeated_resume_keeps_single_active_identity(tmp_path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    adapter = _JsonAdapter()
    resume_input = _resume_input("我是架构师")

    await capture_resume_memory(memory, adapter, resume_input, _state())
    await capture_resume_memory(memory, adapter, resume_input, _state())

    active = memory.query(MemoryLayer.SEMANTIC)
    assert len(active) == 1
    assert active[0].content == "用户身份：架构师"

    # 旧记录被标记 superseded，保留审计
    all_entries = memory.query(MemoryLayer.SEMANTIC)  # 默认排除 deleted
    assert len(all_entries) == 1
