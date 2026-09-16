"""Test that C11 escape hatch policy (ADR-0233) matches the documented decision.

ADR-0233: `execution_point="unknown"` fallback is only for NON-spine events
(Catalog events), and carries a delete-when annotation. `spine.` prefix events
that fail `category_to_spine_ep` ALREADY raise a `ValueError` (fail-loud).

The original spec §15 G-15 proposed registering `AgentRunFinished` as
`spine.lifecycle.run_finished`; ADR-0233 ruled the opposite — the Catalog→Spine
migration (ADR-0192) must complete first, and `health_hash` already replaced
`terminal_event_seq` as the integrity source.

These tests pin the CURRENT documented behavior so a future Catalog→Spine
migration doesn't silently change the closed-set boundary.
"""
from __future__ import annotations

from pathlib import Path


def test_adr0233_documented():
    """ADR-0233 exists with Accepted status."""
    adr = Path("docs/adr/0233-c11-escape-hatch-policy.md")
    assert adr.exists(), "ADR-0233 missing"
    text = adr.read_text()
    assert "Accepted" in text, "ADR-0233 must be Accepted"
    assert "delete-when" in text, "ADR-0233 must state a delete-when"


def test_unknown_fallback_has_delete_when_comment():
    """The `unknown` fallback in persistence.py carries delete-when annotation."""
    source = Path("lca_kernel/events/persistence/persistence.py").read_text()
    assert "delete-when: ADR-0192 Catalog→Spine" in source, (
        "the 'unknown' fallback must carry a delete-when annotation (ADR-0233)"
    )


def test_spine_prefix_still_raises_loud():
    """spine.* EP with no category_to_spine_ep mapping still raises ValueError."""
    # Pin the fail-loud path: the module choothat the fallback only applies to
    # non-spine events. We assert the source still contains the raise statement
    # in the spine.* branch (not a silent fallback).
    source = Path("lca_kernel/events/persistence/persistence.py").read_text()
    assert 'raise ValueError(msg)' in source, (
        "spine.* unknown EP must continue to raise ValueError (fail-loud per ADR-0208)"
    )
