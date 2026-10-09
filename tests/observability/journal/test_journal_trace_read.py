"""TraceInspector + journal round-trip pins.

Rehomed from ``tests/scenario/cli/test_cli_debug_trace.py`` after RA-061
archived the decorative ``cli_debug_command`` plugin seam: the seam's CLI
consumer never existed, but these two cases pin production observability
behaviour (journal IO + inspector), so they stay here instead of dying
with the deleted command.
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.models.observability.journal.journal import (
    AgentRunStarted,
    LlmCallCompleted,
    RunScope,
    StampedEvent,
    TeamRunFinished,
    TeamRunStarted,
)
from lca.infrastructure.observability import TraceInspector
from lca.infrastructure.observability.journal.engine.engine import RunStore
from lca.infrastructure.observability.journal.engine.journal_io import (
    read_journal,
    stamped_to_record,
)


def _scope() -> RunScope:
    return RunScope(trace_id="t", run_id="r")


def _make_journal(tmp_path) -> Path:
    store = RunStore()
    store.append(TeamRunStarted(team_id="t1"))
    store.append(AgentRunStarted(agent_role="tester"))
    store.append(LlmCallCompleted(model="m", latency_ms=42))
    store.append(TeamRunFinished(status="completed"))
    path = tmp_path / "trace.journal"
    with path.open("w", encoding="utf-8") as f:
        for stamped in store.events:
            f.write(json.dumps(stamped_to_record(stamped), ensure_ascii=False))
            f.write("\n")
    return path


def test_inspector_handles_run_completed() -> None:
    events = (
        StampedEvent(
            seq=1,
            ts=1000.0,
            scope=_scope(),
            event=TeamRunStarted(team_id="t1"),
        ),
        StampedEvent(
            seq=2,
            ts=1000.5,
            scope=_scope(),
            event=TeamRunFinished(status="completed"),
        ),
    )
    inspector = TraceInspector(events)
    report = inspector.inspect_trace(focus="all")
    assert report.event_count == 2
    assert report.summary


def test_read_journal_round_trip(tmp_path) -> None:
    path = _make_journal(tmp_path)
    events = read_journal(path)
    assert len(events) == 4
    assert events[0].event_type == "TeamRunStarted"
