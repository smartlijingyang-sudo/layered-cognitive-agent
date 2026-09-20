"""Semantic memory candidate extraction, persistence, and dispatch tests (ADR-0246 PR-3)."""

from __future__ import annotations

import json

import pytest

from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer, ReflectionVerdict
from lca.contracts.models.core.execution.decision import Decision, Observation, Reflection
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.nodes.perceive.fold.fold import PerceiveFoldExecutor
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


def _identity_candidates() -> list[dict[str, object]]:
    return [
        {
            "category": MemoryCategory.IDENTITY.value,
            "content": "用户身份：架构师",
            "confidence": 1.0,
            "source": "user",
            "dedupe_key": "identity:architect",
        }
    ]


@pytest.mark.asyncio
async def test_assistant_memory_persists_typed_semantic_content(tmp_path) -> None:
    mem = AssistantMemory(tmp_path / "asst")
    await mem.update(
        _state("我是架构师"),
        _observation(),
        _reflection(memory_candidates=_identity_candidates()),
    )
    semantic = mem.query(MemoryLayer.SEMANTIC)
    assert len(semantic) == 1
    assert semantic[0].content == "用户身份：架构师"
    assert semantic[0].category is MemoryCategory.IDENTITY
    assert semantic[0].dedupe_key == "identity:architect"
    assert semantic[0].confidence == 1.0

    records = json.loads(
        (tmp_path / "asst" / "memory" / "semantic.json").read_text(encoding="utf-8")
    )
    assert records[0]["category"] == "identity"
    assert records[0]["dedupe_key"] == "identity:architect"
    assert records[0]["metadata"]["source"] == "user"


@pytest.mark.asyncio
async def test_assistant_memory_supersedes_same_dedupe_key(tmp_path) -> None:
    mem = AssistantMemory(tmp_path / "asst")
    await mem.update(
        _state("我是架构师"),
        _observation(),
        _reflection(memory_candidates=_identity_candidates()),
    )
    await mem.update(
        _state("我是高级架构师"),
        _observation(),
        _reflection(
            memory_candidates=[
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
    semantic = mem.query(MemoryLayer.SEMANTIC)
    assert len(semantic) == 1
    assert semantic[0].content == "用户身份：高级架构师"
    assert semantic[0].revision_of is not None

    all_entries = json.loads(
        (tmp_path / "asst" / "memory" / "semantic.json").read_text(encoding="utf-8")
    )
    old = next(e for e in all_entries if e["content"] == "用户身份：架构师")
    assert old["deleted"] is True
    assert old["retired_at_ms"] is not None


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
        runtime={"effect_gateway": gateway, "agent_state": _state("我是架构师")},
        budget={},
        metadata={"plan_ref": "plan:1", "node_id": "remember.write"},
    )
    input_ = NodeInput(
        port_values={
            "decision": _decision(),
            "observation": _observation(),
            "reflection": _reflection(memory_candidates=_identity_candidates()),
            "admitted": True,
            "candidate": _identity_candidates(),
            "effect_gateway": gateway,
        }
    )
    output = await executor.node_execute(context, input_)
    assert len(gateway.executed) == 1
    envelope = gateway.executed[0][0]
    assert envelope.metadata["state"] is not None
    assert envelope.metadata["decision"].decision_id == "decision_1"
    assert output.port_values.get("memory_receipt") == {"admitted": True}


class _RecordingReducer:
    def __init__(self) -> None:
        self.applied: list[object] = []

    def apply_perception(self, state: AgentState, manifest: ContextManifest) -> AgentState:
        state.perceive = manifest  # type: ignore[attr-defined]
        self.applied.append(manifest)
        return state


@pytest.mark.asyncio
async def test_perceive_fold_applies_merged_manifest_to_state() -> None:
    reducer = _RecordingReducer()
    state = _state("我是架构师")
    manifest = ContextManifest(items=())
    executor = PerceiveFoldExecutor()
    context = NodeContext(
        runtime={"state": state, "reducer": reducer},
        budget={},
        metadata={},
    )
    memories = [
        {
            "record_id": "mem_1",
            "content": "用户身份：架构师",
            "memory_type": "semantic",
            "importance": 1.0,
        }
    ]
    output = await executor.node_execute(
        context,
        NodeInput(port_values={"manifest": manifest, "memories": memories}),
    )
    merged = output.port_values["in_assembled_manifest"]
    assert any(item.kind == "memory" for item in merged.items)
    assert reducer.applied == [merged]
