"""PR-3（ADR-0246）：``remember.admit`` 权威度过滤 + ``AssistantMemory`` supersede。"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer, ReflectionVerdict
from lca.contracts.models.core.execution.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.nodes.remember.admit.admit import RememberAdmitExecutor


def _state(task: str) -> AgentState:
    return AgentState(trace_id="trace_t", task=task, budget=Budget())


def _decision() -> Decision:
    return Decision(decision_id="dec_1", action_type="respond", rationale="r", confidence=1.0)


def _observation() -> Observation:
    return Observation(observation_id="obs_1", success=True, payload=None)


def _reflection(candidates: list[dict[str, object]]) -> Reflection:
    return Reflection(
        reflection_id="refl_1",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={"memory_candidates": candidates},
    )


@pytest.mark.asyncio
async def test_admit_accepts_user_candidates_and_rejects_low_confidence_model() -> None:
    executor = RememberAdmitExecutor()
    context = NodeContext(runtime={}, metadata={}, budget=None)

    user_candidates = [
        {"category": "identity", "content": "用户身份：架构师", "confidence": 1.0, "source": "user"}
    ]
    out_user = await executor.node_execute(
        context,
        NodeInput(
            port_values={
                "decision": _decision(),
                "observation": _observation(),
                "reflection": _reflection(user_candidates),
            }
        ),
    )
    assert out_user.port_values["admitted"] is True
    assert out_user.port_values["candidate"] == user_candidates

    model_candidates = [
        {"category": "fact", "content": "模型猜测", "confidence": 0.5, "source": "model"}
    ]
    out_model = await executor.node_execute(
        context,
        NodeInput(
            port_values={
                "decision": _decision(),
                "observation": _observation(),
                "reflection": _reflection(model_candidates),
            }
        ),
    )
    assert out_model.port_values["admitted"] is False
    assert out_model.port_values["candidate"] is None


@pytest.mark.asyncio
async def test_admit_fast_path_rejects_without_candidates() -> None:
    executor = RememberAdmitExecutor()
    context = NodeContext(runtime={}, metadata={}, budget=None)
    refl = Reflection(
        reflection_id="refl_2",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={"fast_path": True},
    )
    out = await executor.node_execute(
        context,
        NodeInput(
            port_values={
                "decision": _decision(),
                "observation": None,
                "reflection": refl,
            }
        ),
    )
    assert out.port_values["admitted"] is False


@pytest.mark.asyncio
async def test_assistant_memory_supersedes_old_fact_on_same_dedupe_key(tmp_path) -> None:
    mem = AssistantMemory(tmp_path / "asst")
    await mem.update(
        _state("我是架构师"),
        _observation(),
        _reflection(
            [
                {
                    "category": MemoryCategory.IDENTITY.value,
                    "content": "用户身份：架构师",
                    "confidence": 1.0,
                    "source": "user",
                    "dedupe_key": "identity:architect",
                }
            ]
        ),
    )
    await mem.update(
        _state("我是高级架构师"),
        _observation(),
        _reflection(
            [
                {
                    "category": MemoryCategory.IDENTITY.value,
                    "content": "用户身份：高级架构师",
                    "confidence": 1.0,
                    "source": "user",
                    "dedupe_key": "identity:architect",
                }
            ]
        ),
    )

    active = mem.query(MemoryLayer.SEMANTIC)
    assert len(active) == 1
    assert active[0].content == "用户身份：高级架构师"
    assert active[0].revision_of is not None
    assert active[0].category is MemoryCategory.IDENTITY
