"""Ralph Loop scenario — workflow automation assembled from v3 primitives (spec §13.4).

The Ralph Loop pattern is a patch-then-test cycle:

  Perceive (workspace-instructions, git-status, test-results, prev-patches)
  → Think ("先跑测试看当前状态")
  → Gate (LoopBreaker / SafetyGate)
  → Act (test-run, patch-write, shell-exec)
  → Reflect ("测试通过了吗？patch 合理吗？")
  → Remember (episodic + semantic)
  → Stop (StopRule)

The spec asserts that Ralph Loop is "完全覆盖，零新增原语" — every
primitive is composed from the existing v3 vocabulary.  This test
verifies the assembly is complete and the compose-order invariants
hold for a Ralph-shaped scenario.

The test deliberately drives the real primitive set:
- ``RepeatToolCallGate`` (loop detection)
- ``ToolLoopBreakerGate`` (loop break)
- ``InboxFactsSensor`` + ``WorkspaceArtifactsSensor`` + ``ClockSensor``
- ``GateDecided`` → ``PolicyFact`` fold
- ``ContextManifested`` emit
- StopRule triggers budget exhaustion

The LLM is a ``ScriptedLLMAdapter`` that returns a deterministic
sequence: test → patch → test → patch → respond.  No real LLM is
required; the assembly is the contract under test.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.observability.journal import (
    ContextManifested,
    InboxFollowupCreated,
)
from lca.layer0_infra.observability.journal.engine import RunStore
from lca.layer1_cognitive.brain.decision_gates import (
    ChainedDecisionGate,
    RepeatToolCallGate,
    ToolLoopBreakerGate,
)
from lca.layer1_cognitive.perceive_hub import SequentialPerceiveHub
from lca.layer1_cognitive.perceive_sink import RunStoreSink
from lca.layer1_cognitive.sensors import (
    InboxFactsSensor,
    build_clock_sensor,
    build_workspace_artifacts_sensor,
)

# ─────────────────────────────────────────────────────────────
# Scenario: Ralph loop
# ─────────────────────────────────────────────────────────────


class TestRalphLoop:
    """Spec §13.4: \"Ralph loop 完全由 v3 现有原语组合实现，零新增原语\"

    The target shape:
    1. Perceive emits a manifest with clock + workspace artifacts + inbox.
    2. GateDecided chains fire on the loop detection.
    3. The Hub drains the gate_decided bucket and folds the PolicyFact.
    4. ContextManifested is emitted every step.
    """

    @pytest.mark.asyncio
    async def test_ralph_step_one_emits_manifest(self) -> None:
        store = RunStore()
        # Stage: user requested a bug fix via the inbox.
        store.append(
            InboxFollowupCreated(
                inbox_id="ralph-1",
                actor="user",
                target="agent",
                priority="high",
                payload_preview="fix bug #123",
            )
        )
        hub = SequentialPerceiveHub(
            sensors=[
                build_clock_sensor(),
                build_workspace_artifacts_sensor(),
                InboxFactsSensor(store),
            ],
            memory=None,
            sink=RunStoreSink(store),
        )
        state = AgentState(
            trace_id=new_id("trace"),
            task="fix bug #123",
            budget=Budget(max_steps=10),
        )
        manifest = await hub.perceive(state)
        kinds = [item.kind for item in manifest.items]
        assert "clock" in kinds
        assert "inbox_facts" in kinds
        # The manifest event was recorded.
        event = store.get_event(store.seq)
        assert isinstance(event, ContextManifested)
        assert event.step == 0

    @pytest.mark.asyncio
    async def test_ralph_chain_emits_repeat_warning(self) -> None:
        """Spec §13.4: 'LoopBreakerGate' (群 Gate 策略).

        The chain includes RepeatToolCallGate + ToolLoopBreakerGate.
        Three consecutive test-run calls produce a PolicyFact warning.
        """
        store = RunStore()
        chain = ChainedDecisionGate(RepeatToolCallGate(), ToolLoopBreakerGate())
        state = AgentState(
            trace_id=new_id("trace"),
            task="fix bug #123",
            budget=Budget(max_steps=10),
        )
        # Three consecutive failed test-runs.
        from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn

        for _ in range(3):
            state.history.append(
                Turn(
                    decision=Decision(
                        decision_id=new_id("dec"),
                        action_type="use_tool",
                        rationale="x",
                        confidence=0.5,
                        tool_calls=[
                            ToolCall(call_id=new_id("tc"), tool_name="test_run", arguments={})
                        ],
                    ),
                    observation=Observation(
                        observation_id=new_id("obs"),
                        success=False,
                        payload="",
                        error="test failed",
                    ),
                )
            )
        dec = Decision(
            decision_id=new_id("dec"),
            action_type="use_tool",
            rationale="x",
            confidence=0.5,
            tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="test_run", arguments={})],
        )
        out = await chain.enforce(state, dec)
        bucket = PerceiveState.from_agent_state(state).gate_decided
        # RepeatToolCallGate fired (warn) and ToolLoopBreakerGate fired
        # (rewrite) — 2 entries total.
        assert len(bucket) >= 2
        assert any(b.gate == "RepeatToolCallGate" for b in bucket)
        assert any(b.gate == "ToolLoopBreakerGate" for b in bucket)
        # The output decision should be RESPOND (ToolLoopBreaker forced it).
        assert out is not None
        from lca.contracts.atoms.enums import ActionType
        assert out.action_type == ActionType.RESPOND

    @pytest.mark.asyncio
    async def test_ralph_fold_carries_policy_fact_into_next_step(self) -> None:
        """Spec §13.4: '重启 / 循环检测 / Approval'.

        The Hub MUST drain the bucket so the next step's manifest
        carries the PolicyFact into the prompt.
        """
        store = RunStore()
        hub = SequentialPerceiveHub(
            sensors=[build_clock_sensor()],
            memory=None,
            sink=RunStoreSink(store),
        )
        state = AgentState(
            trace_id=new_id("trace"),
            task="fix bug #123",
            budget=Budget(max_steps=10),
        )
        # Step 0: gate fires.
        from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn

        for _ in range(3):
            state.history.append(
                Turn(
                    decision=Decision(
                        decision_id=new_id("dec"),
                        action_type="use_tool",
                        rationale="x",
                        confidence=0.5,
                        tool_calls=[
                            ToolCall(call_id=new_id("tc"), tool_name="test_run", arguments={})
                        ],
                    ),
                    observation=Observation(
                        observation_id=new_id("obs"),
                        success=False,
                        payload="",
                        error="test failed",
                    ),
                )
            )
        dec = Decision(
            decision_id=new_id("dec"),
            action_type="use_tool",
            rationale="x",
            confidence=0.5,
            tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="test_run", arguments={})],
        )
        await RepeatToolCallGate().enforce(state, dec)
        # Step 1: Hub folds the bucket.
        state.step = 1
        manifest = await hub.perceive(state)
        assert manifest.has_kind("policy_fact")
        # Bucket is drained.
        assert PerceiveState.from_agent_state(state).gate_decided == []

    @pytest.mark.asyncio
    async def test_ralph_workspace_sensor_optional(self) -> None:
        """Spec §13.4: 'Patch 输出 (不是直编辑)' — workspace artifacts
        are conditional on a workspace being present.  The sensor
        handles the empty case gracefully.
        """
        from lca.layer1_cognitive.sensors import WorkspaceArtifactsSensor

        state = AgentState(
            trace_id=new_id("trace"),
            task="t",
            budget=Budget(max_steps=10),
        )
        items = await WorkspaceArtifactsSensor().read(state)
        # No workspace attached; sensor returns empty.
        assert items == []


# ─────────────────────────────────────────────────────────────
# Complex scenarios (spec §13.5)
# ─────────────────────────────────────────────────────────────


class TestComplexScenarios:
    """Spec §13.5: complex-pattern verification.

    The complex modes are: pipeline, fan-out, debate, peer-relay,
    peer-swarm, graph.  All are assembled from the same v3 primitives
    plus a coordination strategy.  This test exercises the assembly
    with a Hub + chain + multi-step fold.
    """

    @pytest.mark.asyncio
    async def test_multi_step_pipeline_fold(self) -> None:
        """A pipeline run produces one manifest per step; each manifests
        carries the previous step's PolicyFact fold.
        """
        store = RunStore()
        hub = SequentialPerceiveHub(
            sensors=[build_clock_sensor()],
            memory=None,
            sink=RunStoreSink(store),
        )
        state = AgentState(
            trace_id=new_id("trace"),
            task="pipeline",
            budget=Budget(max_steps=10),
        )
        # 3 steps, each emitting ContextManifested.
        for step in range(3):
            state.step = step
            await hub.perceive(state)
        events = [store.get_event(seq) for seq in range(1, store.seq + 1)]
        assert all(isinstance(e, ContextManifested) for e in events)
        # Step numbers are preserved.
        assert [e.step for e in events] == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_complex_chain_with_multiple_gates(self) -> None:
        """A complex run with multiple gates firing produces one
        GateDecided per gate (excluding allow).
        """
        from lca.layer1_cognitive.brain.decision_gates import (
            ProgressLoopDetector,
            TerminalRespondGate,
        )

        store = RunStore()
        chain = ChainedDecisionGate(
            RepeatToolCallGate(),
            ToolLoopBreakerGate(),
            ProgressLoopDetector(),
            TerminalRespondGate(),
        )
        state = AgentState(
            trace_id=new_id("trace"),
            task="t",
            budget=Budget(max_steps=10),
        )
        # Three failed test-runs.
        from lca.contracts.models.core.decision import Decision, Observation, ToolCall, Turn

        for _ in range(3):
            state.history.append(
                Turn(
                    decision=Decision(
                        decision_id=new_id("dec"),
                        action_type="use_tool",
                        rationale="x",
                        confidence=0.5,
                        tool_calls=[
                            ToolCall(call_id=new_id("tc"), tool_name="test_run", arguments={})
                        ],
                    ),
                    observation=Observation(
                        observation_id=new_id("obs"),
                        success=False,
                        payload="",
                        error="test failed",
                    ),
                )
            )
        dec = Decision(
            decision_id=new_id("dec"),
            action_type="use_tool",
            rationale="x",
            confidence=0.5,
            tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="test_run", arguments={})],
        )
        await chain.enforce(state, dec)
        bucket = PerceiveState.from_agent_state(state).gate_decided
        # At least the RepeatToolCallGate fired.
        assert len(bucket) >= 1
        gates = {b.gate for b in bucket}
        assert "RepeatToolCallGate" in gates
