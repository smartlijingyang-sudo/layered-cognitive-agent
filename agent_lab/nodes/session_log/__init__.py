"""session_log nodes — single fact-write surface + framework event tracing.

Importing this package registers:
  - all 19 single-responsibility worker nodes (5 write + 7 trace +
    3 read + 4 hook/durable + 1 identity host via attach_sink)
  - SessionLogEmitterPlugin — bridges runner framework hooks into Session

Public plugin kind: "session_log_emitter"

The Session instance used by all nodes is owned by the internal
``_sink`` module in this package. Tests / runners can call
``configure_session(...)`` to inject a Session; otherwise an
in-memory default is built on first use.

# Node groups (19 + 1 host):

  WRITE — domain facts (5):
    append_decision / append_observation / append_reflection /
    append_tool_result / append_checkpoint

  TRACE — framework lifecycle events (7):
    append.node_start / append.node_end / append.edge_fire /
    append.subgraph_enter / append.subgraph_exit /
    append.before_compile / append.after_compile

  READ — fold/snapshot/seal (3):
    snapshot.events / fold.header / session.seq

  HOOK — observer + consumption (3):
    register.observer / fanout.observers / consume.events

  DURABLE — JSONL sink (2):
    attach.sink / flush.sink
"""
# Worker nodes
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

from agent_lab.nodes.session_log.attach_sink.plugin import AttachSink
from agent_lab.nodes.session_log.flush_sink.plugin import FlushSink

# Plugin (bridges runner hooks into Session). Importing the submodule
# triggers @register_plugin on SessionLogEmitterPlugin.
from agent_lab.nodes.session_log import plugin as _plugin  # noqa: F401

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
    # DURABLE
    "AttachSink", "FlushSink",
]
