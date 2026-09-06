"""Meta-event taxonomy SSOT tests."""

from __future__ import annotations

from lca.contracts.observability.meta_event_taxonomy import (
    DEBUG_RUN_META_FAMILIES,
    META_EVENT_PRODUCER_SEAMS,
    SKILL_SESSION_EVENTS,
    SKILL_SPINE_EXECUTION_POINTS,
    TOOL_SESSION_EVENTS,
    all_session_meta_event_types,
    classify_spine_event_key,
)
from lca.contracts.observability.skill_meta_ep_closure import SKILL_META_EVENT_POINTS


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
