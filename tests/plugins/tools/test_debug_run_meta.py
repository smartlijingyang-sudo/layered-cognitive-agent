"""debug-run meta family summary tests."""

from __future__ import annotations

from lca.plugins.tools.diagnostics.debug.debug_run import _spine_meta_family_counts


def test_spine_meta_family_counts_groups_events() -> None:
    events = [
        {"execution_point": "llm.call.start"},
        {"execution_point": "llm.call.end"},
        {"execution_point": "phase.tool.call.start"},
        {"execution_point": "body.sandbox.enter"},
        {"category": "skill.loaded.v1", "payload": {}},
        {"category": "assistant.run.bound.v1", "payload": {}},
    ]
    counts = dict(_spine_meta_family_counts(events))
    assert counts.get("llm") == 2
    assert counts.get("tool") == 1
    assert counts.get("sandbox") == 1
    assert counts.get("skill") == 1
    assert counts.get("assistant") == 1
