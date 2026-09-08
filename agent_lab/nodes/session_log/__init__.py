"""session_log nodes — single fact-write surface + framework event tracing.

Three groups (18 nodes total):

  WRITE — domain facts (5):
    append_decision / append_observation / append_reflection /
    append_tool_result / append_checkpoint

  TRACE — framework lifecycle events (7):
    append_node_start / append_node_end / append_edge_fire /
    append_subgraph_enter / append_subgraph_exit /
    append_before_compile / append_after_compile

  READ — fold/snapshot/seal (4):
    snapshot_events / fold_header / session_seq /
    fanout_observers (read+trigger)

  HOOK — observer registration / pull-based consumption (2):
    register_observer / consume_events

All nodes share the singleton Session exposed by
``agent_lab._session_holder``. Configure at boot via
``configure_session(...)``; otherwise an in-memory default is built.

event_type whitelist (C11 closed set):
  - domain:    decision.v1, observation.v1, reflection.v1,
               tool.result.v1, checkpoint.v1
  - framework: graph.node_start.v1, graph.node_end.v1,
               graph.edge_fire.v1, graph.subgraph_enter.v1,
               graph.subgraph_exit.v1, graph.before_compile.v1,
               graph.after_compile.v1
"""
from agent_lab.nodes.session_log.append_decision.plugin import AppendDecision
from agent_lab.nodes.session_log.append_observation.plugin import AppendObservation
from agent_lab.nodes.session_log.append_reflection.plugin import AppendReflection
from agent_lab.nodes.session_log.append_tool_result.plugin import AppendToolResult
from agent_lab.nodes.session_log.append_checkpoint.plugin import AppendCheckpoint

from agent_lab.nodes.session_log.append_node_start.plugin import AppendNodeStart
from agent_lab.nodes.session_log.append_node_end.plugin import AppendNodeEnd
from agent_lab.nodes.session_log.append_edge_fire.plugin import AppendEdgeFire
from agent_lab.nodes.session_log.append_subgraph_enter.plugin import AppendSubgraphEnter
from agent_lab.nodes.session_log.append_subgraph_exit.plugin import AppendSubgraphExit
from agent_lab.nodes.session_log.append_before_compile.plugin import AppendBeforeCompile
from agent_lab.nodes.session_log.append_after_compile.plugin import AppendAfterCompile

from agent_lab.nodes.session_log.snapshot_events.plugin import SnapshotEvents
from agent_lab.nodes.session_log.fold_header.plugin import FoldHeader
from agent_lab.nodes.session_log.session_seq.plugin import SessionSeq

from agent_lab.nodes.session_log.register_observer.plugin import RegisterObserver
from agent_lab.nodes.session_log.fanout_observers.plugin import FanoutObservers
from agent_lab.nodes.session_log.consume_events.plugin import ConsumeEvents

__all__ = [
    # WRITE
    "AppendDecision", "AppendObservation", "AppendReflection",
    "AppendToolResult", "AppendCheckpoint",
    # TRACE
    "AppendNodeStart", "AppendNodeEnd", "AppendEdgeFire",
    "AppendSubgraphEnter", "AppendSubgraphExit",
    "AppendBeforeCompile", "AppendAfterCompile",
    # READ
    "SnapshotEvents", "FoldHeader", "SessionSeq",
    # HOOK
    "RegisterObserver", "FanoutObservers", "ConsumeEvents",
]
