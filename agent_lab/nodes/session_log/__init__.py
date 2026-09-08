"""session_log nodes — the single fact-write surface for agent_lab.

Append-only contract (per ADR-0186/0191/0194):
  5 append_* nodes — one per event_type (decision/observation/reflection/
                                       tool_result/checkpoint)
  3 read nodes — snapshot_events / fold_header / session_seq
  1 hook node  — register_observer (fan-out to durable sinks)

All 9 nodes share the singleton Session exposed by
``agent_lab._session_holder``. Configure it at boot via
``configure_session(...)``; nodes otherwise use the default in-memory
Session.
"""
from agent_lab.nodes.session_log.append_decision.plugin import AppendDecision
from agent_lab.nodes.session_log.append_observation.plugin import AppendObservation
from agent_lab.nodes.session_log.append_reflection.plugin import AppendReflection
from agent_lab.nodes.session_log.append_tool_result.plugin import AppendToolResult
from agent_lab.nodes.session_log.append_checkpoint.plugin import AppendCheckpoint
from agent_lab.nodes.session_log.snapshot_events.plugin import SnapshotEvents
from agent_lab.nodes.session_log.fold_header.plugin import FoldHeader
from agent_lab.nodes.session_log.session_seq.plugin import SessionSeq
from agent_lab.nodes.session_log.register_observer.plugin import RegisterObserver

__all__ = [
    "AppendDecision", "AppendObservation", "AppendReflection",
    "AppendToolResult", "AppendCheckpoint",
    "SnapshotEvents", "FoldHeader", "SessionSeq",
    "RegisterObserver",
]
