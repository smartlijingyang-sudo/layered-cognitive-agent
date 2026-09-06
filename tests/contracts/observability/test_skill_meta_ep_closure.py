"""Skill meta EP closure regression tests."""

from __future__ import annotations

from lca.contracts.observability.cordis_event_table import lookup_cordis_name
from lca.contracts.observability.skill_meta_ep_closure import (
    SKILL_META_EVENT_POINTS,
    all_skill_meta_event_descriptors,
)


def test_skill_meta_closure_count() -> None:
    assert len(SKILL_META_EVENT_POINTS) == 4
    assert len(set(SKILL_META_EVENT_POINTS)) == 4


def test_skill_meta_descriptors_match_closure() -> None:
    descriptors = all_skill_meta_event_descriptors()
    assert {d.type_name for d in descriptors} == set(SKILL_META_EVENT_POINTS)


def test_skill_meta_cordis_table() -> None:
    for ep in SKILL_META_EVENT_POINTS:
        entry = lookup_cordis_name(ep)
        assert entry.cordis_name == f"agent.{ep}"
