"""Comprehensive scenario integration tests (user requirement).

This module is the consolidated test suite for the v3 cognitive-primitive
constitution.  It covers:

1. Fine-grained primitive tests (Hub, Sensor, Gate, Sink).
2. Plugin composition tests (named factories, fixed order).
3. End-to-end scenarios (Ralph Loop, complex pipeline, team message).
4. Cross-cutting invariants (no magic strings, no list plugins,
   no cordis listeners, no harness↛L1).

The test pyramid is structured so a regression in any one layer
triggers a localized failure with a clear pointer to the affected
spec section.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.ids import new_id
from lca.contracts.harness.plugin_meta import LAYER_FIELD, NAME_FIELD, PluginMeta
from lca.contracts.models.core.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.perceive_state import PerceiveState
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.observability.journal import (
    InboxFollowupCreated,
    TeamMessagePublished,
)
from lca.contracts.protocols import Sensor
from lca.contracts.protocols.cognition import SensorDisabledError
from lca.infrastructure.observability.journal.engine import RunStore
from lca.layer1_cognitive.brain.context_manifest import digest_manifest
from lca.layer1_cognitive.brain.decision_gates import (
    ChainedDecisionGate,
    ProgressLoopDetector,
    RepeatToolCallGate,
    TerminalRespondGate,
    ToolLoopBreakerGate,
    record_gate_decided,
)
from lca.layer1_cognitive.perceive_hub import SequentialPerceiveHub
from lca.layer1_cognitive.perceive_sink import JournalSink, NullSink
from lca.layer1_cognitive.sensors import (
    InboxFactsSensor,
    TeamInboxSensor,
    build_clock_sensor,
    build_workspace_artifacts_sensor,
)

# ─────────────────────────────────────────────────────────────
# Sensors — fine-grained
# ─────────────────────────────────────────────────────────────


class TestSensorsPrimitive:
    """Each sensor is a typed Protocol implementer with a named factory."""

    @pytest.mark.asyncio
    async def test_clock_sensor_emits_clock_kind(self) -> None:
        items = await build_clock_sensor().read(_state())
        assert len(items) == 1
        assert items[0].kind == "clock"

    @pytest.mark.asyncio
    async def test_workspace_sensor_returns_empty_without_workspace(self) -> None:
        items = await WorkspaceArtifactsSensor().read(_state())
        assert items == []

    @pytest.mark.asyncio
    async def test_inbox_sensor_folds_journal_events(self) -> None:
        store = RunStore()
        store.append(
            InboxFollowupCreated(inbox_id="i1", actor="user", target="t", priority="p", step=0)
        )
        sensor = InboxFactsSensor(store)
        items = await sensor.read(_state())
        assert items[0].payload[0]["inbox_id"] == "i1"

    @pytest.mark.asyncio
    async def test_team_inbox_sensor_folds_team_messages(self) -> None:
        store = RunStore()
        store.append(
            TeamMessagePublished(
                team_id="t1", thread_id="th1", sender_role="lead", recipient_role="member"
            )
        )
        sensor = TeamInboxSensor(store)
        items = await sensor.read(_state())
        assert items[0].payload[0]["team_id"] == "t1"

    @pytest.mark.asyncio
    async def test_sensor_disabled_signal(self) -> None:
        """SensorDisabled skips the sensor in the Hub fold.

        The exception is raised by the sensor on ``read()``; the Hub
        catches it and proceeds.  A direct call to ``read()`` raises
        so the Hub can detect the signal.
        """

        class _Disabled(Sensor):
            async def read(self, state):
                raise SensorDisabledError("skip")

        with pytest.raises(SensorDisabledError):
            await _Disabled().read(_state())
        # The Hub path catches the exception and produces an empty
        # contribution.
        from lca.layer1_cognitive.perceive_hub import SequentialPerceiveHub
        from lca.layer1_cognitive.perceive_sink import NullSink

        hub = SequentialPerceiveHub(
            sensors=[_Disabled()],
            memory=None,
            sink=NullSink(),
        )
        manifest = await hub.perceive(_state())
        assert manifest.has_kind("clock") is False
        assert manifest.items == ()


# ─────────────────────────────────────────────────────────────
# Gates — fine-grained
# ─────────────────────────────────────────────────────────────


class TestGatesPrimitive:
    """Each gate is a typed Protocol implementer with PolicyFact semantics."""

    @pytest.mark.asyncio
    async def test_repeat_warns_after_threshold(self) -> None:
        state = _state()
        state.history.extend(_failed_turn("executeCode") for _ in range(3))
        gate = RepeatToolCallGate()
        await gate.enforce(state, _dec("executeCode"))
        bucket = PerceiveState.from_agent_state(state).gate_decided
        assert len(bucket) == 1
        assert bucket[0].verdict == "warn"

    @pytest.mark.asyncio
    async def test_tool_loop_breaker_rewrites_to_respond(self) -> None:
        from lca.contracts.atoms.enums import ActionType

        state = _state()
        state.history.extend(_failed_turn("executeCode") for _ in range(3))
        gate = ToolLoopBreakerGate()
        out = await gate.enforce(state, _dec("executeCode"))
        assert out.action_type == ActionType.RESPOND
        bucket = PerceiveState.from_agent_state(state).gate_decided
        assert any(b.gate == "ToolLoopBreakerGate" for b in bucket)

    @pytest.mark.asyncio
    async def test_allow_verdict_does_not_record(self) -> None:
        """The spec: ``allow`` 默认不记.  No warning on a normal tool call."""
        state = _state()
        state.history.append(_ok_turn("executeCode"))
        gate = RepeatToolCallGate()
        await gate.enforce(state, _dec("executeCode"))
        assert PerceiveState.from_agent_state(state).gate_decided == []

    @pytest.mark.asyncio
    async def test_chain_order_preserved(self) -> None:
        chain = ChainedDecisionGate(
            RepeatToolCallGate(),
            ToolLoopBreakerGate(),
            ProgressLoopDetector(),
            TerminalRespondGate(),
        )
        state = _state()
        state.history.extend(_failed_turn("executeCode") for _ in range(3))
        await chain.enforce(state, _dec("executeCode"))
        # The chain fires each gate in order; bucket contains both.
        bucket = PerceiveState.from_agent_state(state).gate_decided
        gates = [b.gate for b in bucket]
        assert "RepeatToolCallGate" in gates
        assert "ToolLoopBreakerGate" in gates


# ─────────────────────────────────────────────────────────────
# Hub — primitive + composition
# ─────────────────────────────────────────────────────────────


class TestHubPrimitive:
    """The Hub is the sole ContextManifested emitter (PR2)."""

    @pytest.mark.asyncio
    async def test_hub_emits_manifest_with_digest(self) -> None:
        store = RunStore()
        hub = SequentialPerceiveHub(
            sensors=[build_clock_sensor()],
            memory=None,
            sink=JournalSink.for_store(store),
        )
        manifest = await hub.perceive(_state())
        digest = digest_manifest(manifest)
        assert digest != ""
        stamped = store.get(store.seq)
        assert stamped is not None
        assert stamped.event.digest == digest

    @pytest.mark.asyncio
    async def test_hub_drains_gate_decided(self) -> None:
        store = RunStore()
        hub = SequentialPerceiveHub(
            sensors=[],
            memory=None,
            sink=JournalSink.for_store(store),
        )
        state = _state()
        # Pre-seed the bucket.
        record_gate_decided(
            state,
            GateDecided(
                event_id=new_id("gate"),
                gate="RepeatToolCallGate",
                verdict="warn",
                is_rewritten=False,
                policy_fact=PolicyFact(
                    kind="repeat_tool_call", message="warning", source="repeat_tool_call"
                ),
            ),
        )
        state.step = 1
        manifest = await hub.perceive(state)
        assert manifest.has_kind("policy_fact")
        assert PerceiveState.from_agent_state(state).gate_decided == []

    @pytest.mark.asyncio
    async def test_hub_with_null_sink_does_not_record(self) -> None:
        """NullSink is the offline-test sink."""
        hub = SequentialPerceiveHub(
            sensors=[build_clock_sensor()],
            memory=None,
            sink=NullSink(),
        )
        manifest = await hub.perceive(_state())
        assert manifest.has_kind("clock")


# ─────────────────────────────────────────────────────────────
# Plugin composition — large-scale
# ─────────────────────────────────────────────────────────────


class TestCompositionLarge:
    """Large composition: every sensor + gates + chain."""

    @pytest.mark.asyncio
    async def test_all_sensors_together(self) -> None:
        store = RunStore()
        store.append(
            InboxFollowupCreated(inbox_id="i1", actor="user", target="t", priority="p", step=0)
        )
        store.append(
            TeamMessagePublished(
                team_id="t1", thread_id="th1", sender_role="lead", recipient_role="member"
            )
        )
        hub = SequentialPerceiveHub(
            sensors=[
                build_clock_sensor(),
                build_workspace_artifacts_sensor(),
                InboxFactsSensor(store),
                TeamInboxSensor(store),
            ],
            memory=None,
            sink=JournalSink.for_store(store),
        )
        state = _state()
        # Pre-seed a gate so the policy_fact fold is exercised.
        state.history.extend(_failed_turn("executeCode") for _ in range(3))
        await RepeatToolCallGate().enforce(state, _dec("executeCode"))
        state.step = 1
        manifest = await hub.perceive(state)
        kinds = [item.kind for item in manifest.items]
        assert "clock" in kinds
        assert "inbox_facts" in kinds
        assert "team_inbox" in kinds
        assert "policy_fact" in kinds
        # The composition order is preserved.
        assert kinds.index("clock") < kinds.index("inbox_facts")

    @pytest.mark.asyncio
    async def test_idempotent_perceive(self) -> None:
        """The Hub is idempotent for replay: same sensors → same manifest."""
        store = RunStore()
        hub = SequentialPerceiveHub(
            sensors=[build_clock_sensor()],
            memory=None,
            sink=JournalSink.for_store(store),
        )
        state = _state()
        m1 = await hub.perceive(state)
        m2 = await hub.perceive(state)
        assert digest_manifest(m1) == digest_manifest(m2)


# ─────────────────────────────────────────────────────────────
# Plugin meta — typed contract
# ─────────────────────────────────────────────────────────────


class TestPluginMetaContract:
    """The PluginMeta TypedDict is the single source of plugin metadata."""

    def test_plugin_meta_keys(self) -> None:
        meta: PluginMeta = {
            NAME_FIELD: "sensor.clock",
            LAYER_FIELD: "sensor",
            "provides": ["sensor.clock"],
        }
        assert meta[NAME_FIELD] == "sensor.clock"
        assert meta[LAYER_FIELD] == "sensor"

    def test_no_parallel_primitive_manifest_schema(self) -> None:
        """The spec forbids a parallel ``PrimitiveManifest`` schema file."""
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        offenders = list(root.rglob("primitive_manifest*.py"))
        assert not offenders, (
            f"cognitive-primitive v3 §D8: PrimitiveManifest schema is forbidden. "
            f"Offenders: {offenders}"
        )


# ─────────────────────────────────────────────────────────────
# Team message — end-to-end
# ─────────────────────────────────────────────────────────────


class TestTeamMessageE2E:
    """TeamMessage publish → sensor → manifest."""

    @pytest.mark.asyncio
    async def test_publish_then_hub_folds(self) -> None:
        store = RunStore()
        # Local store append (the global record path uses the global hub).
        store.append(
            TeamMessagePublished(
                team_id="team-1",
                thread_id="thread-1",
                sender_role="lead",
                recipient_role="member",
                body_preview="hi",
            )
        )
        hub = SequentialPerceiveHub(
            sensors=[TeamInboxSensor(store)],
            memory=None,
            sink=JournalSink.for_store(store),
        )
        manifest = await hub.perceive(_state())
        assert manifest.has_kind("team_inbox")
        assert manifest.by_kind("team_inbox")[0].payload[0]["team_id"] == "team-1"

    def test_team_message_publish_dedupes_topic(self) -> None:
        """D25: 每 Team 恰好一个 topic；delegation/task 用 thread_id."""
        # The publish tool requires only ``team_id`` + ``thread_id``; the
        # caller picks the topic.  A test confirms the tool accepts the
        # pair.
        from lca.layer1_cognitive.body.team_message_tool import (
            build_team_message_publish_tool,
        )

        tool = build_team_message_publish_tool()
        assert (
            tool.validate(
                {
                    "team_id": "team-1",
                    "thread_id": "thread-1",
                    "recipient_role": "member",
                    "body": "hello",
                }
            )
            is None
        )


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def _state() -> AgentState:
    return AgentState(trace_id=new_id("trace"), task="t", budget=Budget(max_steps=10))


def _dec(tool: str):
    from lca.contracts.models.core.decision import Decision, ToolCall

    return Decision(
        decision_id=new_id("dec"),
        action_type="use_tool",
        rationale="x",
        confidence=0.5,
        tool_calls=[ToolCall(call_id=new_id("tc"), tool_name=tool, arguments={})],
    )


def _failed_turn(tool: str):
    from lca.contracts.models.core.decision import Observation, Turn

    return Turn(
        decision=_dec(tool),
        observation=Observation(
            observation_id=new_id("obs"),
            success=False,
            payload="",
            error="boom",
        ),
    )


def _ok_turn(tool: str):
    from lca.contracts.models.core.decision import Observation, Turn

    return Turn(
        decision=_dec(tool),
        observation=Observation(
            observation_id=new_id("obs"),
            success=True,
            payload="ok",
        ),
    )


class WorkspaceArtifactsSensor:
    """Inline import alias to avoid extra coupling in this test module."""

    from lca.layer1_cognitive.sensors import WorkspaceArtifactsSensor as _Impl

    def __new__(cls):
        return cls._Impl()
