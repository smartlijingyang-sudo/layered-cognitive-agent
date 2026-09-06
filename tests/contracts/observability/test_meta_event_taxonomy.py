"""Meta-event taxonomy SSOT tests."""

from __future__ import annotations

from lca.contracts.observability.closure.skill_meta_ep_closure import SKILL_META_EVENT_POINTS
from lca.contracts.observability.cursor.loop_cursor import PhaseName
from lca.contracts.observability.event.meta_event_taxonomy import (
    COGNITION_SPINE_EPS,
    DEBUG_RUN_META_FAMILIES,
    LLM_SPINE_EPS,
    META_EVENT_PRODUCER_SEAMS,
    PHASE_FOLD_SPINE_EPS,
    SKILL_SESSION_EVENTS,
    SKILL_SPINE_EXECUTION_POINTS,
    TOOL_SESSION_EVENTS,
    all_session_meta_event_types,
    classify_spine_event_key,
)


def test_phase_name_has_six_semantic_phases_without_gate() -> None:
    """ADR-0194 P2-01: Gate is Think sub-chain; not a loop-cursor graph node."""
    assert set(PhaseName.__args__) == {
        "perceive",
        "think",
        "act",
        "reflect",
        "remember",
        "stop",
    }
    assert "gate" not in PhaseName.__args__


def test_phase_fold_spine_eps_align_with_phase_name() -> None:
    """ADR-0194 P2-02: taxonomy phase fold EPs match 6-step PhaseName closure."""
    expected = {f"phase.{phase}.fold" for phase in PhaseName.__args__}
    assert set(PHASE_FOLD_SPINE_EPS) == expected
    assert "phase.gate.fold" not in PHASE_FOLD_SPINE_EPS


def test_llm_spine_eps_exclude_gate_phase_and_brain_gate() -> None:
    """ADR-0194 P2-02: gate observability is cognition sub-span, not LLM spine."""
    assert "brain.gate.start" not in LLM_SPINE_EPS
    assert "brain.gate.end" not in LLM_SPINE_EPS
    assert not any(ep.startswith("phase.gate") for ep in LLM_SPINE_EPS)


def test_cognition_spine_eps_include_think_gate_subspan() -> None:
    """ADR-0194 P2-05: brain.gate.* retired; think.gate.* is Think sub-span."""
    assert "think.gate.start" in COGNITION_SPINE_EPS
    assert "think.gate.end" in COGNITION_SPINE_EPS
    assert "brain.gate.start" not in COGNITION_SPINE_EPS


def test_session_meta_types_include_gate_decided() -> None:
    types = all_session_meta_event_types()
    assert "gate.decided.v1" in types


def test_classify_spine_event_key_think_gate() -> None:
    assert classify_spine_event_key("think.gate.start") == "prompt"


def test_skill_spine_closure_matches_taxonomy() -> None:
    assert SKILL_SPINE_EXECUTION_POINTS == SKILL_META_EVENT_POINTS


def test_session_meta_types_include_new_events() -> None:
    types = all_session_meta_event_types()
    assert "skill.searched.v1" in types
    assert "tool.schema.published.v1" in types
    assert "prompt.section.published.v1" in types
    assert "assistant.run.bound.v1" in types
    assert set(SKILL_SESSION_EVENTS) <= types
    assert set(TOOL_SESSION_EVENTS) <= types


def test_classify_spine_event_key() -> None:
    assert classify_spine_event_key("llm.call.start") == "llm"
    assert classify_spine_event_key("phase.tool.call.end") == "tool"
    assert classify_spine_event_key("body.sandbox.enter") == "sandbox"
    assert classify_spine_event_key("skill.package.installed") == "skill"
    assert classify_spine_event_key("assistant.created") == "assistant"
    assert classify_spine_event_key("prompt_assembler.assemble.end") == "prompt"


def test_debug_run_families_non_empty() -> None:
    assert len(DEBUG_RUN_META_FAMILIES) >= 6


def test_producer_seams_cover_core_domains() -> None:
    domains = {slot.domain for slot in META_EVENT_PRODUCER_SEAMS}
    assert {"skill", "tool", "assistant", "integration", "llm", "cognition", "sandbox"} <= domains
