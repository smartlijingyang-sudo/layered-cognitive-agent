"""End-to-end v3 integration test (cumulative proof).

Drives the full v3 stack in one run:
1. PerceiveHub with all sensors + null sink
2. Sentinel event flow: InboxFollowup → TeamMessage → ToolLoop
3. GateDecided → PolicyFact fold
4. RepeatToolCallGate + ToolLoopBreakerGate
5. The full chain (DecisionGate)
6. ExecutionEnvelope minting
7. Final manifest digest stable across replays

Used as the cumulative "do everything at once" proof for the v3
spec §Risks / "PR-by-PR canary" mitigation.
"""

from __future__ import annotations

import asyncio

import pytest

from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.execution import (
    ExecutionEnvelope,
    envelope_from_decision,
    find_terminal_tool_invoked,
)
from lca.contracts.models.core.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.perception import ContextItem
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.observability.journal import (
    InboxFollowupCreated,
    TeamMessagePublished,
)
from lca.contracts.protocols import Sensor
from lca.contracts.protocols.cognition import SensorDisabled
from lca.contracts.models.core.decision import Decision, ToolCall, Turn, Observation
from lca.layer0_infra.observability.journal.engine import RunStore
from lca.layer1_cognitive.brain.context_manifest import digest_manifest
from lca.layer1_cognitive.brain.decision_gates import (
    ChainedDecisionGate,
    RepeatToolCallGate,
    ToolLoopBreakerGate,
    record_gate_decided,
)
from lca.layer1_cognitive.perceive_hub import SequentialPerceiveHub
from lca.layer1_cognitive.perceive_sink import RunStoreSink
from lca.layer1_cognitive.sensors import (
    InboxFactsSensor,
    TeamInboxSensor,
    build_clock_sensor,
    build_workspace_artifacts_sensor,
)


class TestFullV3Integration:
    """Run the full v3 stack end-to-end and verify the spine."""

    @pytest.mark.asyncio
    async def test_full_v3_spine_runs_clean(self) -> None:
        store = RunStore()
        # 1. Stage upstream events.
        store.append(
            InboxFollowupCreated(
                inbox_id="i1", actor="user", target="agent", priority="normal", step=0
            )
        )
        store.append(
            TeamMessagePublished(
                team_id="team-1",
                thread_id="thread-1",
                sender_role="lead",
                recipient_role="member",
                step=0,
                body_preview="first msg",
            )
        )
        # 2. Build the Hub with every sensor.
        hub = SequentialPerceiveHub(
            sensors=[
                build_clock_sensor(),
                build_workspace_artifacts_sensor(),
                InboxFactsSensor(store),
                TeamInboxSensor(store),
            ],
            memory=None,
            sink=RunStoreSink(store),
        )
        # 3. Run step 1 — no gates have fired yet.
        state = _state()
        manifest = await hub.perceive(state)
        kinds = [item.kind for item in manifest.items]
        assert "clock" in kinds
        assert "inbox_facts" in kinds
        assert "team_inbox" in kinds
        # 4. Run a tool loop that triggers the chain.
        chain = ChainedDecisionGate(RepeatToolCallGate(), ToolLoopBreakerGate())
        state.history.extend(_failed_turn("executeCode") for _ in range(3))
        await chain.enforce(state, _dec("executeCode"))
        # 5. Step 2 — Hub folds the gate_decided bucket.
        state.step = 1
        manifest = await hub.perceive(state)
        assert manifest.has_kind("policy_fact")
        # 6. The ContextManifested events were recorded (only the
        # Hub emits, so the last 2 events are manifests).
        all_events = [
            store.get_event(seq) for seq in range(1, store.seq + 1)
        ]
        context_manifested_events = [
            e for e in all_events if type(e).__name__ == "ContextManifested"
        ]
        assert len(context_manifested_events) == 2
        # 7. Each manifest has a digest.
        assert all(e.digest != "" for e in context_manifested_events)

    @pytest.mark.asyncio
    async def test_envelope_mints_for_each_tool_call(self) -> None:
        """PR6: ExecutionEnvelope carries capability_grant + idempotency_key."""
        env = envelope_from_decision("executeCode", {"code": "print(1)"})
        assert env.capability_grant == "default"
        assert env.tool_name == "executeCode"
        assert env.arguments == {"code": "print(1)"}
        assert env.is_idempotent() is False
        assert env.requires_approval() is False

    def test_envelope_with_idempotency_key(self) -> None:
        env = ExecutionEnvelope(
            capability_grant="write",
            tool_name="write_file",
            arguments={"path": "x"},
            idempotency_key="abc-123",
        )
        assert env.is_idempotent() is True

    def test_envelope_with_approval_requirement(self) -> None:
        env = ExecutionEnvelope(
            capability_grant="exec",
            tool_name="run_command",
            arguments={"cmd": "rm -rf /"},
            approval_requirement="high_risk",
        )
        assert env.requires_approval() is True

    def test_find_terminal_tool_invoked(self) -> None:
        """PR6: terminal tool check is used for resume idempotency."""
        history = [
            _dec("executeCode"),
            _dec("terminal_respond"),
        ]
        # Wrap the decisions in Turn so the type checker is happy.
        turns = [
            Turn(
                decision=dec,
                observation=Observation(
                    observation_id=new_id("obs"),
                    success=True,
                    payload="",
                ),
            )
            for dec in history
        ]
        assert find_terminal_tool_invoked(turns) is True

    @pytest.mark.asyncio
    async def test_hub_digest_stable_across_runs(self) -> None:
        """Perception is deterministic for the same sensor set + state."""
        store = RunStore()
        hub = SequentialPerceiveHub(
            sensors=[build_clock_sensor()],
            memory=None,
            sink=RunStoreSink(store),
        )
        # Two runs of the same state produce the same digest.
        state = _state()
        m1 = await hub.perceive(state)
        m2 = await hub.perceive(state)
        assert digest_manifest(m1) == digest_manifest(m2)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def _state() -> AgentState:
    return AgentState(trace_id=new_id("trace"), task="t", budget=Budget(max_steps=10))


def _dec(tool: str) -> Decision:
    return Decision(
        decision_id=new_id("dec"),
        action_type="use_tool",
        rationale="x",
        confidence=0.5,
        tool_calls=[ToolCall(call_id=new_id("tc"), tool_name=tool, arguments={})],
    )


def _failed_turn(tool: str) -> Turn:
    return Turn(
        decision=_dec(tool),
        observation=Observation(
            observation_id=new_id("obs"),
            success=False,
            payload="",
            error="boom",
        ),
    )
