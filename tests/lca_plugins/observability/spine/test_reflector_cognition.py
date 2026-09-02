"""Tests for cognition spine reflector (PR-3.2).

Asserts that cognition layer entry points emit the canonical
``EXECUTION_POINTS`` events when a spine is wired, and that the
emit helpers are safe no-ops when no spine is wired.
"""

from __future__ import annotations

import asyncio

import pytest

from lca.infrastructure.observability.spine.context import SpineContext
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.infrastructure.observability.spine.event_spine import EventSpine

# ── helpers ──────────────────────────────────────────────────────────


class _CaptureSink:
    """Minimal sink that records every EventRecord in order."""

    def __init__(self) -> None:
        self.records: list[EventRecord] = []

    def write(self, record: EventRecord) -> None:
        self.records.append(record)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def _make_spine() -> tuple[EventSpine, _CaptureSink]:
    sink = _CaptureSink()
    spine = EventSpine(sinks=[sink])
    SpineContext.set_run("cognition-reflector-test")
    return spine, sink


def _eps_by_point(records: list[EventRecord]) -> dict[str, list[EventRecord]]:
    out: dict[str, list[EventRecord]] = {}
    for rec in records:
        out.setdefault(rec.execution_point, []).append(rec)
    return out


# ── safe no-ops without active spine ────────────────────────────────


def test_emit_helpers_are_safe_when_no_spine_wired() -> None:
    """Without an active spine, the helpers must not raise."""
    from lca.plugins.observability.spine.reflectors.cognition import (
        emit_brain_think_end,
        emit_brain_think_start,
        emit_critic_eval_end,
        emit_critic_eval_start,
        emit_memory_read,
        emit_memory_write,
        emit_reasoner_reason_end,
        emit_reasoner_reason_start,
        emit_skill_router_route,
        emit_synthesizer_merge,
    )

    # All of these must complete without raising, regardless of state.
    emit_brain_think_start(state_id="s1")
    emit_brain_think_end(state_id="s1", outcome="success")
    emit_critic_eval_start(state_id="s1")
    emit_critic_eval_end(state_id="s1", outcome="success")
    emit_reasoner_reason_start(state_id="s1")
    emit_reasoner_reason_end(state_id="s1", outcome="success")
    emit_synthesizer_merge(state_id="s1", candidate_count=0)
    emit_skill_router_route(state_id="s1", template="react_prompt")
    emit_memory_read(state_id="s1")
    emit_memory_write(state_id="s1", layer="working")


# ── helpers forward to active spine ──────────────────────────────────


def test_emit_helpers_forward_to_active_spine() -> None:
    """When a spine is set, helpers emit via spine.append."""
    from lca.plugins.observability.spine.reflectors.cognition import (
        emit_brain_think_end,
        emit_brain_think_start,
        set_active_spine,
    )

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        emit_brain_think_start(state_id="s1")
        emit_brain_think_end(state_id="s1", outcome="success")
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["brain.think.start", "brain.think.end"]
    assert sink.records[1].outcome == "success"


# ── modular_brain.think emits brain.think.start/end ─────────────────


def test_modular_brain_think_emits_brain_think_events() -> None:
    """Brain.think wraps with brain.think.start/end (PR-3.2)."""
    from lca.cognition.brain.modular_brain import ModularBrain
    from lca.contracts.models.core.state import AgentState
    from lca.plugins.observability.spine.reflectors.cognition import set_active_spine

    spine, sink = _make_spine()
    set_active_spine(spine)

    # Build a Minimal ModularBrain with stub collaborators. The think
    # delegation goes through the think_pipeline; we stub it to return a
    # synthetic Decision so we don't need a full Reasoner/Classifier.
    from lca.contracts.atoms.enums import ActionType
    from lca.contracts.models.core.decision import Decision

    class _StubThink:
        async def decide(self, **_kwargs) -> Decision:
            return Decision(
                decision_id="d1",
                action_type=ActionType.RESPOND,
                rationale="stub",
                confidence=1.0,
            )

    brain = ModularBrain.__new__(ModularBrain)
    # Bypass __init__ — only think() is exercised; assign just enough.
    brain.reasoner = None  # type: ignore[assignment]
    brain.critic = None
    brain.skill_router = None
    brain._decision_gate = None
    brain._agent_gates = None
    brain.reducer = None
    brain.classifier = None  # type: ignore[assignment]
    brain._think_pipeline = _StubThink()  # type: ignore[assignment]
    brain._reflection_pipeline = None  # type: ignore[assignment]

    try:
        state = AgentState(trace_id="t1", task="x", budget=None)
        decision = _run(brain.think(state))
        assert decision.action_type == ActionType.RESPOND
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["brain.think.start", "brain.think.end"]


def _run(coro):
    """Run an awaitable synchronously (test helper)."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ── reasoner emits reasoner.reason.start/end ────────────────────────


def test_reasoner_emits_reasoner_reason_events() -> None:
    """Reasoner.generate_thoughts wraps with reasoner.reason.start/end."""
    # Patch execute_llm_turn to a stub for this test.
    import lca.cognition.brain.reasoner as reasoner_mod
    from lca.cognition.brain.reasoner import PromptReasoner
    from lca.contracts.models.core.llm import LLMResponse
    from lca.contracts.models.core.state import AgentState
    from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
    from lca.plugins.observability.spine.reflectors.cognition import set_active_spine

    original = reasoner_mod.execute_llm_turn

    async def _stub_execute(*args, **kwargs):
        return LLMResponse(text="stub", tool_calls=(), finish_reason="stop")

    reasoner_mod.execute_llm_turn = _stub_execute
    try:
        spine, sink = _make_spine()
        set_active_spine(spine)
        try:
            reasoner = PromptReasoner(
                llm=None,  # unused — execute_llm_turn is stubbed
                role_profile=RoleProfile(
                    role="r",
                    goal="g",
                    backstory="b",
                    tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
                ),
                tools_desc="",
                templates={"react_prompt": "ROLE:{role} GOAL:{goal} BACKSTORY:{backstory}"},
            )
            state = AgentState(trace_id="t1", task="x", budget=None)
            _run(reasoner.generate_thoughts(state))
        finally:
            set_active_spine(None)
            reasoner_mod.execute_llm_turn = original
    except Exception:
        reasoner_mod.execute_llm_turn = original
        raise

    points = [r.execution_point for r in sink.records]
    assert points == [
        "prompt_assembler.assemble.start",
        "prompt_assembler.assemble.end",
        "reasoner.reason.start",
        "reasoner.reason.end",
    ]


# ── critic emits critic.eval.start/end ──────────────────────────────


def test_critic_emits_critic_eval_events() -> None:
    """Critic.critique wraps with critic.eval.start/end."""
    from lca.cognition.brain.critic import SimpleCritic
    from lca.contracts.atoms.ids import new_id
    from lca.contracts.models.core.decision import Observation
    from lca.contracts.models.core.state import AgentState
    from lca.plugins.observability.spine.reflectors.cognition import set_active_spine

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        critic = SimpleCritic()
        state = AgentState(trace_id="t1", task="x", budget=None)
        obs = Observation(observation_id=new_id("obs"), success=True, payload="ok", extra={})
        _run(critic.critique(state, obs))
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["critic.eval.start", "critic.eval.end"]


def test_null_critic_emits_critic_eval_events() -> None:
    """NullCritic also wraps with critic.eval.start/end (consistent instrumentation)."""
    from lca.cognition.brain.null_critic import NullCritic
    from lca.contracts.atoms.ids import new_id
    from lca.contracts.models.core.decision import Observation
    from lca.contracts.models.core.state import AgentState
    from lca.plugins.observability.spine.reflectors.cognition import set_active_spine

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        critic = NullCritic()
        state = AgentState(trace_id="t1", task="x", budget=None)
        obs = Observation(observation_id=new_id("obs"), success=True, payload=None, extra={})
        _run(critic.critique(state, obs))
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["critic.eval.start", "critic.eval.end"]


# ── synthesizer emits synthesizer.merge ─────────────────────────────


def test_synthesizer_emits_synthesizer_merge() -> None:
    """Synthesizer.synthesize emits a single synthesizer.merge event."""
    from lca.cognition.brain.synthesizer import ConcatSynthesizer
    from lca.contracts.models.core.lifecycle import TaskStatus
    from lca.contracts.models.core.result import Result
    from lca.contracts.models.core.state import Budget
    from lca.plugins.observability.spine.reflectors.cognition import set_active_spine

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        synth = ConcatSynthesizer()
        c1 = Result(
            trace_id="t1",
            status=TaskStatus.COMPLETED,
            final_state_ref="",
            total_steps=1,
            budget_used=Budget(),
            output="first",
            lessons=[],
        )
        _run(synth.synthesize("objective", [c1]))
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["synthesizer.merge"]
    payload = sink.records[0].payload
    assert payload.get("candidate_count") == 1


# ── skill_router emits skill_router.route ───────────────────────────


def test_skill_router_emits_skill_router_route() -> None:
    """SkillRouter.route emits a single skill_router.route event."""
    from lca.cognition.brain.skill_router import KeywordSkillRouter
    from lca.contracts.models.core.state import AgentState
    from lca.plugins.observability.spine.reflectors.cognition import set_active_spine

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        router = KeywordSkillRouter(
            rules={"research_prompt": ["研究", "research"]},
            default_template="react_prompt",
        )
        state = AgentState(trace_id="t1", task="research something", budget=None)
        template = _run(router.route(state))
        assert template == "research_prompt"
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["skill_router.route"]
    payload = sink.records[0].payload
    assert payload.get("template") == "research_prompt"


# ── memory emits memory.read / memory.write ─────────────────────────


def test_memory_perceive_emits_memory_read() -> None:
    """MemorySystem.perceive wraps with memory.read."""
    from lca.cognition.memory.simple_memory import SimpleMemorySystem
    from lca.contracts.models.core.state import AgentState
    from lca.plugins.observability.spine.reflectors.cognition import set_active_spine

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        mem = SimpleMemorySystem()
        state = AgentState(trace_id="t1", task="x", budget=None)
        _run(mem.perceive(state))
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["memory.read"]


def test_memory_commit_emits_memory_write() -> None:
    """MemorySystem.commit wraps accepted writes with memory.write."""
    from lca.cognition.memory.policy import MemoryAuthority, MemoryWrite
    from lca.cognition.memory.simple_memory import SimpleMemorySystem
    from lca.contracts.atoms.enums import MemoryLayer, MemoryRecordKind
    from lca.contracts.atoms.ids import new_id
    from lca.plugins.observability.spine.reflectors.cognition import set_active_spine

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        mem = SimpleMemorySystem()
        write = MemoryWrite(
            record_id=new_id("mem"),
            layer=MemoryLayer.WORKING,
            authority=MemoryAuthority.MODEL_INFERENCE,
            content="stub",
            confidence=1.0,
            kind=MemoryRecordKind.GENERIC,
        )
        result = mem.commit((write,))
        assert len(result.accepted) == 1
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert "memory.write" in points


# ── exception in inner call still emits end event ───────────────────


def test_critic_eval_end_emitted_on_inner_exception() -> None:
    """If the underlying critique() raises, the spine still receives
    critic.eval.end with outcome='failure'. The exception propagates.

    SimpleCritic's wrapper is exercised by patching ``_evaluate`` to raise
    on the same instance.
    """
    from lca.cognition.brain.critic import SimpleCritic
    from lca.contracts.atoms.ids import new_id
    from lca.contracts.models.core.decision import Observation
    from lca.contracts.models.core.state import AgentState
    from lca.plugins.observability.spine.reflectors.cognition import set_active_spine

    class _Boom(SimpleCritic):
        def _evaluate(self, state, observation):  # type: ignore[override]
            raise RuntimeError("critic boom")

    spine, sink = _make_spine()
    set_active_spine(spine)
    try:
        critic = _Boom()
        state = AgentState(trace_id="t1", task="x", budget=None)
        obs = Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=None,
            extra={},
        )
        with pytest.raises(RuntimeError, match="critic boom"):
            _run(critic.critique(state, obs))
    finally:
        set_active_spine(None)

    points = [r.execution_point for r in sink.records]
    assert points == ["critic.eval.start", "critic.eval.end"]
    assert sink.records[1].outcome == "failure"
