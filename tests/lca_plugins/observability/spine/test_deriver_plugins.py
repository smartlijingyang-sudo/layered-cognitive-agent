"""Tests for spine deriver plugins (step_tree / narrative / graph / live_tail).

Covers Manifest id/provides for each module, GraphDeriver digraph flush,
and FD-2 style ``on_event`` safety for the remaining derivers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from lca.harness.plugin_declaration import definition_from_plugin
from lca.infrastructure.observability.spine.derivers.graph import GraphDeriver
from lca.infrastructure.observability.spine.event_record import EventRecord
from lca.plugins.observability.spine.derivers import (
    graph,
    live_tail,
    narrative,
    step_tree,
)
from lca.plugins.observability.spine.derivers.step_tree import StepTreeDeriverPlugin

_BASE_KWARGS: dict[str, object] = {
    "execution_point": "brain.think.start",
    "channel": "fact",
    "span_id": "lca-span-00000001",
    "parent_span_id": None,
    "sequence": 1,
    "epoch": 1,
    "causality_id": "sha256:abc",
    "outcome": None,
    "when": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
    "when_corrected": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
    "prev_event_hash": None,
    "run_id": "r-test",
    "step_id": "s-test",
    "payload": {},
}


def _make_event(**overrides: object) -> EventRecord:
    kwargs = dict(_BASE_KWARGS)
    kwargs.update(overrides)
    return EventRecord(**kwargs)  # type: ignore[arg-type]


# ── Manifest declarations ────────────────────────────────────────────


def test_step_tree_module_declares_plugin() -> None:
    assert hasattr(step_tree, "setup")
    definition = definition_from_plugin(step_tree.setup, module=__name__)
    assert definition.id == "spine.deriver.step_tree"
    assert "step_tree" in tuple(definition.provided_capability_keys)


def test_narrative_module_declares_plugin() -> None:
    assert hasattr(narrative, "setup")
    definition = definition_from_plugin(narrative.setup, module=__name__)
    assert definition.id == "spine.deriver.narrative"
    assert "narrative" in tuple(definition.provided_capability_keys)


def test_graph_module_declares_plugin() -> None:
    assert hasattr(graph, "setup")
    definition = definition_from_plugin(graph.setup, module=__name__)
    assert definition.id == "spine.deriver.graph"
    assert "graph" in tuple(definition.provided_capability_keys)


def test_live_tail_module_declares_plugin() -> None:
    assert hasattr(live_tail, "setup")
    definition = definition_from_plugin(live_tail.setup, module=__name__)
    assert definition.id == "spine.deriver.live_tail"
    assert "live_tail" in tuple(definition.provided_capability_keys)


# ── GraphDeriver behaviour ───────────────────────────────────────────


def test_graph_deriver_on_event_and_flush_writes_digraph(tmp_path: Path) -> None:
    out = tmp_path / "phase_graph.dot"
    deriver = GraphDeriver(output_path=out)
    deriver.on_event(_make_event(execution_point="brain.think.start", sequence=1))
    deriver.on_event(_make_event(execution_point="brain.think.end", sequence=2))
    deriver.on_event(_make_event(execution_point="brain.gate.start", sequence=3))
    written = deriver.flush()
    assert written == out
    text = out.read_text(encoding="utf-8")
    assert "digraph" in text
    assert "brain.think.start" in text
    assert "->" in text


def test_graph_deriver_terminal_event_auto_flushes(tmp_path: Path) -> None:
    out = tmp_path / "phase_graph.dot"
    deriver = GraphDeriver(output_path=out)
    deriver.on_event(_make_event(execution_point="kernel.run.start", sequence=1))
    deriver.on_event(_make_event(execution_point="kernel.run.stop", sequence=2, channel="control"))
    assert out.exists()
    assert "digraph" in out.read_text(encoding="utf-8")


# ── on_event does not raise ──────────────────────────────────────────


def test_step_tree_on_event_does_not_raise() -> None:
    deriver = StepTreeDeriverPlugin()
    deriver.on_event(_make_event())
    deriver.flush()
    assert deriver.event_count == 1


def test_narrative_on_event_does_not_raise(tmp_path: Path) -> None:
    from lca.infrastructure.observability.journal.step.narrative_writer import (
        StepNarrativeWriter,
    )
    from lca.infrastructure.observability.spine.derivers.narrative import (
        NarrativeDeriver,
    )

    deriver = NarrativeDeriver(writer=StepNarrativeWriter(tmp_path / "n.md"))
    deriver.on_event(_make_event())


def test_live_tail_on_event_does_not_raise() -> None:
    from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
    from lca.infrastructure.observability.spine.derivers.live_tail import (
        LiveTailDeriver,
    )

    deriver = LiveTailDeriver(tail=LiveTail())
    deriver.on_event(_make_event())
