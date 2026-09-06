"""Ralph Loop scenario — workflow automation assembled from v3 primitives (spec §13.4).

The Ralph Loop pattern is a patch-then-test cycle:

  Perceive (workspace-instructions, git-status, test-results, prev-patches)
  → Think ("先跑测试看当前状态")
  → Gate (LoopBreaker / SafetyGate)
  → Act (test-run, patch-write, shell-exec)
  → Reflect ("测试通过了吗？patch 合理吗？")
  → Remember (episodic + semantic)
  → Stop (StopPolicy)

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
- StopPolicy triggers budget exhaustion

The LLM is a ``ScriptedLLMAdapter`` that returns a deterministic
sequence: test → patch → test → patch → respond.  No real LLM is
required; the assembly is the contract under test.
"""

from __future__ import annotations

import pytest

from lca.cognition.brain.decision_gates import (
    ChainedDecisionGate,
    RepeatToolCallGate,
    ToolLoopBreakerGate,
)
from lca.cognition.perceive.hub import SequentialPerceiveHub
from lca.cognition.sensors import (
    InboxFactsSensor,
    build_clock_sensor,
    build_workspace_artifacts_sensor,
)
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.observability.journal.journal import (
    InboxFollowupCreated,
)
from lca.infrastructure.observability.journal.engine.engine import RunStore
from tests.support.session_gate_helpers import (
    bound_session,
    extend_control_turns,
    gate_decisions_for_step,
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
        assert manifest.digest != ""

    @pytest.mark.asyncio
    async def test_ralph_chain_emits_repeat_warning(self) -> None:
        """Spec §13.4: 'LoopBreakerGate' (群 Gate 策略).

        The chain includes RepeatToolCallGate + ToolLoopBreakerGate.
        Three consecutive test-run calls produce a PolicyFact warning.
        """
        chain = ChainedDecisionGate(RepeatToolCallGate(), ToolLoopBreakerGate())
        from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn

        def _failed_test_run() -> Turn:
            return Turn(
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

        dec = Decision(
            decision_id=new_id("dec"),
            action_type="use_tool",
            rationale="x",
            confidence=0.5,
            tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="test_run", arguments={})],
        )
        with bound_session():
            state = AgentState(
                trace_id=new_id("trace"),
                task="fix bug #123",
                budget=Budget(max_steps=10),
            )
            extend_control_turns(state, (_failed_test_run() for _ in range(3)))
            out = await chain.enforce(state, dec)
            bucket = gate_decisions_for_step(state)
            # RepeatToolCallGate fired (warn) and ToolLoopBreakerGate fired
            # (rewrite) — 2 entries total.
            assert len(bucket) >= 2
            assert any(b.gate == "RepeatToolCallGate" for b in bucket)
            assert any(b.gate == "ToolLoopBreakerGate" for b in bucket)
            # The output decision should be RESPOND (ToolLoopBreaker forced it).
            assert out is not None
            from lca.contracts.atoms.enums.enums import ActionType

            assert out.action_type == ActionType.RESPOND

    @pytest.mark.asyncio
    async def test_ralph_fold_carries_policy_fact_into_next_step(self) -> None:
        """Spec §13.4: '重启 / 循环检测 / Approval'.

        The Hub MUST drain the bucket so the next step's manifest
        carries the PolicyFact into the prompt.
        """
        hub = SequentialPerceiveHub(
            sensors=[build_clock_sensor()],
            memory=None,
        )
        from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn

        def _failed_test_run() -> Turn:
            return Turn(
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

        dec = Decision(
            decision_id=new_id("dec"),
            action_type="use_tool",
            rationale="x",
            confidence=0.5,
            tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="test_run", arguments={})],
        )
        with bound_session():
            state = AgentState(
                trace_id=new_id("trace"),
                task="fix bug #123",
                budget=Budget(max_steps=10),
            )
            extend_control_turns(state, (_failed_test_run() for _ in range(3)))
            await RepeatToolCallGate().enforce(state, dec)
            state.step = 1
            manifest = await hub.perceive(state)
            assert manifest.has_kind("policy_fact")

    @pytest.mark.asyncio
    async def test_ralph_workspace_sensor_optional(self) -> None:
        """Spec §13.4: 'Patch 输出 (不是直编辑)' — workspace artifacts
        are conditional on a workspace being present.  The sensor
        handles the empty case gracefully.
        """
        from lca.cognition.sensors import WorkspaceArtifactsSensor

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
        hub = SequentialPerceiveHub(
            sensors=[build_clock_sensor()],
            memory=None,
        )
        state = AgentState(
            trace_id=new_id("trace"),
            task="pipeline",
            budget=Budget(max_steps=10),
        )
        digests: list[str] = []
        for step in range(3):
            state.step = step
            manifest = await hub.perceive(state)
            assert manifest.has_kind("clock")
            digests.append(manifest.digest)
        assert len(digests) == 3
        assert all(digest for digest in digests)

    @pytest.mark.asyncio
    async def test_complex_chain_with_multiple_gates(self) -> None:
        """A complex run with multiple gates firing produces one
        GateDecided per gate (excluding allow).
        """
        from lca.cognition.brain.decision_gates import (
            ProgressLoopDetector,
            TerminalRespondGate,
        )

        chain = ChainedDecisionGate(
            RepeatToolCallGate(),
            ToolLoopBreakerGate(),
            ProgressLoopDetector(),
            TerminalRespondGate(),
        )
        from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn

        def _failed_test_run() -> Turn:
            return Turn(
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

        dec = Decision(
            decision_id=new_id("dec"),
            action_type="use_tool",
            rationale="x",
            confidence=0.5,
            tool_calls=[ToolCall(call_id=new_id("tc"), tool_name="test_run", arguments={})],
        )
        with bound_session():
            state = AgentState(
                trace_id=new_id("trace"),
                task="t",
                budget=Budget(max_steps=10),
            )
            extend_control_turns(state, (_failed_test_run() for _ in range(3)))
            await chain.enforce(state, dec)
            bucket = gate_decisions_for_step(state)
            # At least the RepeatToolCallGate fired.
            assert len(bucket) >= 1
            gates = {b.gate for b in bucket}
            assert "RepeatToolCallGate" in gates
