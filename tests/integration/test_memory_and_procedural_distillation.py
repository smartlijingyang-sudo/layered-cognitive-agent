"""Integration tests for declarative memory nodes, admission gate, and universal procedural distillation (ADR-0244 PR-5)."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.models.cognition.boundary import ProceduralMemoryCandidate
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    Reflection,
    ToolCall,
    Turn,
)
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.perceive.memory_retrieve.memory_retrieve import PerceiveMemoryRetrieveExecutor
from lca.nodes.reflect.score.score import ReflectScoreExecutor
from lca.nodes.remember.admit.admit import RememberAdmitExecutor
from lca.nodes.remember.write.write import RememberWriteExecutor


@dataclass
class DummyAgentState:
    turns: list[Turn] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


class MockEffectGateway:
    def __init__(self) -> None:
        self.dispatched_envelopes: list[Any] = []

    async def dispatch(self, envelope: Any) -> dict[str, Any]:
        self.dispatched_envelopes.append(envelope)
        return {"status": "persisted", "idempotency_key": envelope.idempotency_key}


class MockMemoryProvider:
    async def retrieve(self, manifest: Any) -> list[dict[str, Any]]:
        return [{"memory_id": "mem_001", "content": "Prior user preference: always use strict type hints"}]


async def test_perceive_memory_retrieve_with_provider() -> None:
    """PerceiveMemoryRetrieveExecutor retrieves contextual memories from memory_provider."""
    executor = PerceiveMemoryRetrieveExecutor()
    provider = MockMemoryProvider()
    manifest = ContextManifest(items=())
    context = NodeContext(runtime={"memory_provider": provider}, metadata={}, budget=None)
    node_input = NodeInput(port_values={"manifest": manifest})

    output = await executor.node_execute(context, node_input)

    assert output.port_values["manifest"] is manifest
    memories = output.port_values["memories"]
    assert len(memories) == 1
    assert memories[0]["memory_id"] == "mem_001"
    assert "strict type hints" in memories[0]["content"]


async def test_perceive_memory_retrieve_without_provider() -> None:
    """PerceiveMemoryRetrieveExecutor gracefully outputs empty memories when provider is absent."""
    executor = PerceiveMemoryRetrieveExecutor()
    context = NodeContext(runtime={}, metadata={}, budget=None)
    node_input = NodeInput(port_values={"manifest": None})

    output = await executor.node_execute(context, node_input)

    assert output.port_values["manifest"] is None
    assert output.port_values["memories"] == ()


async def test_reflect_score_universal_meta_feature_distillation() -> None:
    """ReflectScoreExecutor identifies multi-step tool success without hardcoded heuristics."""
    executor = ReflectScoreExecutor()
    context = NodeContext(runtime={}, metadata={}, budget=None)

    # Prepare state with 2 successful tool actions
    turn_1 = Turn(
        decision=Decision(
            decision_id="d1",
            action_type="tool",
            rationale="tool 1",
            confidence=1.0,
            tool_calls=[ToolCall(call_id="c1", tool_name="code_interpreter", arguments={})],
        ),
        observation=Observation(observation_id="o1", success=True, payload=None),
    )
    turn_2 = Turn(
        decision=Decision(
            decision_id="d2",
            action_type="tool",
            rationale="tool 2",
            confidence=1.0,
            tool_calls=[ToolCall(call_id="c2", tool_name="exportFile", arguments={})],
        ),
        observation=Observation(observation_id="o2", success=True, payload=None),
    )
    state = DummyAgentState(turns=[turn_1, turn_2])
    current_obs = Observation(
        observation_id="o3",
        success=True,
        payload=None,
        extra={"generated_files": ("report.pdf",)},
    )

    node_input = NodeInput(port_values={"observation": current_obs, "state": state})
    output = await executor.node_execute(context, node_input)

    reflection = output.port_values["reflection"]
    assert isinstance(reflection, Reflection)
    candidate = reflection.extra.get("procedural_candidate")
    assert candidate is not None
    assert isinstance(candidate, ProceduralMemoryCandidate)
    assert candidate.tool_sequence == ("code_interpreter", "exportFile")
    assert candidate.confidence >= 0.9
    assert candidate.evidence_count >= 2


def test_no_hardcoded_skill_names_in_nodes() -> None:
    """Strict check: ensure no hardcoded skill names or intent regexes in cognitive nodes."""
    for cls in (ReflectScoreExecutor, RememberAdmitExecutor, RememberWriteExecutor, PerceiveMemoryRetrieveExecutor):
        source = inspect.getsource(cls)
        assert "skill-creator" not in source, f"Hardcoded 'skill-creator' found in {cls.__name__}"
        assert "做成一个skill" not in source, f"Hardcoded Chinese regex found in {cls.__name__}"


async def test_remember_admit_gate_verifies_authority_and_filters_noise() -> None:
    """RememberAdmitExecutor admits verified candidates and rejects failed/fast-path reflections."""
    admit_executor = RememberAdmitExecutor()
    context = NodeContext(runtime={}, metadata={}, budget=None)

    decision = Decision(decision_id="dec_1", action_type="respond", rationale="test", confidence=1.0)
    candidate = ProceduralMemoryCandidate(
        candidate_id="cand_1",
        workflow_summary="Two-step pipeline",
        tool_sequence=("fetch", "process"),
    )

    # 1. Success tool observation -> Admitted
    succ_obs = Observation(observation_id="obs_succ", success=True, payload=None)
    refl_with_cand = Reflection(
        reflection_id="refl_1",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={"procedural_candidate": candidate},
    )
    input_succ = NodeInput(port_values={"decision": decision, "observation": succ_obs, "reflection": refl_with_cand})
    out_succ = await admit_executor.node_execute(context, input_succ)
    assert out_succ.port_values["admitted"] is True
    assert out_succ.port_values["candidate"] == candidate

    # 2. Failed tool observation -> Rejected
    fail_obs = Observation(observation_id="obs_fail", success=False, payload=None)
    input_fail = NodeInput(port_values={"decision": decision, "observation": fail_obs, "reflection": refl_with_cand})
    out_fail = await admit_executor.node_execute(context, input_fail)
    assert out_fail.port_values["admitted"] is False
    assert out_fail.port_values["candidate"] is None

    # 3. Pure text fast-path (no candidates) -> Zero-cost rejection
    refl_noop = Reflection(
        reflection_id="refl_2",
        verdict=ReflectionVerdict.ON_TRACK,
        extra={"fast_path": True},
    )
    input_noop = NodeInput(port_values={"decision": decision, "observation": None, "reflection": refl_noop})
    out_noop = await admit_executor.node_execute(context, input_noop)
    assert out_noop.port_values["admitted"] is False
    assert out_noop.port_values["candidate"] is None


async def test_remember_write_c10_narrow_door() -> None:
    """RememberWriteExecutor obeys C10: only dispatches envelope when admitted."""
    write_executor = RememberWriteExecutor()
    gateway = MockEffectGateway()
    context = NodeContext(runtime={"effect_gateway": gateway}, metadata={"plan_ref": "plan1", "node_id": "n1"}, budget=None)

    decision = Decision(decision_id="dec_1", action_type="respond", rationale="test", confidence=1.0)
    obs = Observation(observation_id="obs_1", success=True, payload=None)
    refl = Reflection(reflection_id="refl_1", verdict=ReflectionVerdict.ON_TRACK)

    # Case A: admitted is False -> No envelope minted, zero side effects
    input_rejected = NodeInput(
        port_values={
            "decision": decision,
            "observation": obs,
            "reflection": refl,
            "admitted": False,
            "candidate": None,
        }
    )
    out_rejected = await write_executor.node_execute(context, input_rejected)
    assert out_rejected.port_values["envelope"] is None
    assert out_rejected.port_values["memory_receipt"] is None
    assert len(gateway.dispatched_envelopes) == 0

    # Case B: admitted is True -> Envelope minted and dispatched to EffectGateway
    candidate = ProceduralMemoryCandidate(
        candidate_id="cand_2",
        workflow_summary="SOP",
        tool_sequence=("step1",),
    )
    input_admitted = NodeInput(
        port_values={
            "decision": decision,
            "observation": obs,
            "reflection": refl,
            "admitted": True,
            "candidate": candidate,
        }
    )
    out_admitted = await write_executor.node_execute(context, input_admitted)
    envelope = out_admitted.port_values["envelope"]
    assert envelope is not None
    assert envelope.provider == "effect.memory"
    assert envelope.metadata["candidate"] == candidate
    assert len(gateway.dispatched_envelopes) == 1
    receipt = out_admitted.port_values["memory_receipt"]
    assert receipt == {"status": "persisted", "idempotency_key": envelope.idempotency_key}


def test_subgraphs_declarative_schema_and_node_wiring() -> None:
    """Verify perceive_subgraph.yaml and remember_subgraph.yaml YAML declarations."""
    repo_root = Path(__file__).resolve().parents[2]

    # Perceive subgraph
    perceive_path = repo_root / "bundles" / "perceive" / "perceive_subgraph.yaml"
    with open(perceive_path, encoding="utf-8") as f:
        perceive_data = yaml.safe_load(f)

    node_ids = [n["id"] for n in perceive_data["nodes"]]
    assert "phase.perceive.observe" in node_ids
    assert "phase.perceive.memory_retrieve" in node_ids
    assert "phase.perceive.fold" in node_ids

    edges = [(e["from"], e["to"]) for e in perceive_data["edges"]]
    assert ("phase.perceive.observe", "phase.perceive.memory_retrieve") in edges
    assert ("phase.perceive.memory_retrieve", "phase.perceive.fold") in edges

    # Remember subgraph
    remember_path = repo_root / "bundles" / "remember" / "remember_subgraph.yaml"
    with open(remember_path, encoding="utf-8") as f:
        remember_data = yaml.safe_load(f)

    r_node_ids = [n["id"] for n in remember_data["nodes"]]
    assert "phase.remember.admit" in r_node_ids
    assert "phase.remember.write" in r_node_ids
    assert "phase.remember.fold" in r_node_ids

    r_edges = [(e["from"], e["to"]) for e in remember_data["edges"]]
    assert ("phase.remember.admit", "phase.remember.write") in r_edges
    assert ("phase.remember.write", "phase.remember.fold") in r_edges
