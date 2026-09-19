"""Semantic memory candidate extraction, persistence, and dispatch tests (PR-4)."""

from __future__ import annotations

import json

import pytest

from lca.contracts.atoms.enums.enums import MemoryLayer, ReflectionVerdict
from lca.contracts.models.core.execution.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.nodes.reflect.score.score import _extract_semantic_candidate
from lca.nodes.remember.write.write import RememberWriteExecutor


def _state(task: str) -> AgentState:
    return AgentState(trace_id="trace_t", task=task, budget=Budget())


def _reflection(**extra: object) -> Reflection:
    return Reflection(
        reflection_id="refl_1",
        verdict=ReflectionVerdict.ON_TRACK,
        extra=extra,
    )


def _observation() -> Observation:
    return Observation(observation_id="obs_1", success=True, payload=None)


def _decision() -> Decision:
    return Decision(
        decision_id="decision_1",
        action_type="respond",
        rationale="ack",
        confidence=1.0,
        response_text="记住了",
    )


def test_extract_semantic_candidate_user_directive() -> None:
    cand = _extract_semantic_candidate(_state("记住：我的昵称是老板，我的名字叫李超。"))
    assert cand is not None
    assert cand["source"] == "user"
    assert cand["confidence"] == 1.0
    assert "老板" in str(cand["content"])


def test_extract_semantic_candidate_non_directive_none() -> None:
    assert _extract_semantic_candidate(_state("什么是快手电商？")) is None


@pytest.mark.asyncio
async def test_assistant_memory_persists_semantic_content(tmp_path) -> None:
    mem = AssistantMemory(tmp_path / "asst")
    await mem.update(
        _state("记住：以后叫我老板"),
        _observation(),
        _reflection(
            memory_candidate={"content": "以后叫我老板", "source": "user", "confidence": 1.0}
        ),
    )
    semantic = mem.query(MemoryLayer.SEMANTIC)
    assert len(semantic) == 1
    assert semantic[0].content == "以后叫我老板"
    records = json.loads(
        (tmp_path / "asst" / "memory" / "semantic.json").read_text(encoding="utf-8")
    )
    assert records[0]["metadata"]["source"] == "user"


class _RecordingGateway:
    """Fake EffectDispatcher that records the executed envelope."""

    def __init__(self) -> None:
        self.executed: list[tuple[object, object]] = []

    async def execute(
        self,
        envelope: object,
        policy: object,
        *,
        state: object | None = None,
        decision: object | None = None,
    ) -> dict[str, bool]:
        del state, decision
        self.executed.append((envelope, policy))
        return {"admitted": True}


@pytest.mark.asyncio
async def test_remember_write_dispatches_via_execute() -> None:
    gateway = _RecordingGateway()
    executor = RememberWriteExecutor()
    context = NodeContext(
        runtime={"effect_gateway": gateway},
        budget={},
        metadata={"plan_ref": "plan:1", "node_id": "remember.write"},
    )
    input_ = NodeInput(
        port_values={
            "decision": _decision(),
            "observation": _observation(),
            "reflection": _reflection(
                memory_candidate={"content": "以后叫我老板", "source": "user", "confidence": 1.0}
            ),
            "admitted": True,
            "candidate": {"content": "以后叫我老板", "source": "user", "confidence": 1.0},
            "effect_gateway": gateway,
        }
    )
    output = await executor.node_execute(context, input_)
    assert len(gateway.executed) == 1
    assert output.port_values.get("memory_receipt") == {"admitted": True}
