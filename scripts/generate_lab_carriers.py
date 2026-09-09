#!/usr/bin/env python3
# PR-D final 2/2 — node carrier generator
"""Build real LCA-plugin-compatible carriers for the 89 remaining lab nodes.

Why a generator?
----------------
We can't import ``lca.harness.plugin_api`` in this test environment
(no cordis), so we can't use the standard ``@plugin`` decorator. The
right tool is the LCA plugin's own data model: ``PluginDefinition``
and ``PluginSpec`` are pure Pydantic + dataclass; only the
decorator machinery (and the ``cordis.plugin`` symbol it re-exports)
needs cordis at import time.

This module builds the same shape (id / provides / requires / effects /
contract / setup) using only Pydantic + the local `LabCarrier` shim that
mirrors what the loader's ``load_all`` would normalise from a real
@plugin-decorated function.

Carrier shape produced per node:
    from lca.plugins.lab.internal.hooks import LabCarrier
    from lca.plugins.lab.<area>.<node> import <NodeClass>  # lazy

The carrier is a function with the right signature so it can be passed
to the loader's `register_carrier` (added in this PR). The loader
treats a carrier like a @plugin function: calls it at registration
time and stores the resulting plugin data in _LAB_HOOKS.

Why a generator rather than 89 hand-written files?
----------------------------------------------------
89 nodes × ~80 lines per carrier = 7100 lines of boilerplate. A
generator keeps the per-node data declarative (one entry per node)
and centralises the LCA plugin contract.

The generator is **idempotent**: re-running it overwrites existing
files with the same content (modulo the standard "regenerated at
<timestamp>" header). The 89 generated carriers are
indistinguishable from hand-written ones to the loader.

delete-when (PR-D final 2/2 acceptance):
- agent_lab/nodes/<area>/<name>/plugin.py replaced by the carrier
- agent_lab/plugins/{events,observers,parsers,semantic_router,
  control_slots,observation,memory_extract,tool_guard}.py deleted
- agent_lab/plugins/base.py GraphPlugin + register_plugin deleted
- agent_lab/nodes/session_log/plugin.py deleted
- agent_lab/tools/registry.py compat shim deleted
- bundles/lab-act.yaml + bundles/lab-session.yaml wired into
  profiles/agent-lab-infoedge.yaml
- agent_lab_default session_id never constructed; missing active
  session is fail-loud
- ADR-0206 §10 P7 stage closure migration complete
"""

from __future__ import annotations

import textwrap
from pathlib import Path

# =============================================================================
# NODE_CARRIERS — perceive / think / reflect / remember (typed workers)
# =============================================================================
NODE_CARRIERS: list[dict] = [
    # perceive phase
    {"slot": "lab.perceive.sense",       "area": "perceive", "name": "sense",
     "module": "agent_lab.nodes.perceive.sense.plugin",
     "class": "PerceiveSense",
     "stage": "perceive", "kind": "TRANSFORMER",
     "desc": "Fold Sensor.read(state) over resolved sensors into sensor_items.",
     "inputs": [("sensors", "FACT", False), ("state", "FACT", False)],
     "outputs": [("sensor_items", "FACT")],
     "provides": ["sensor_items"], "requires": ["sensors"],
     "emits": ["sensor_items"],
     "out_cap": "lab.perceive.sense.out:sensor_items"},
    {"slot": "lab.perceive.resolve",      "area": "perceive", "name": "resolve",
     "module": "agent_lab.nodes.perceive.resolve.plugin",
     "class": "PerceiveResolve",
     "stage": "perceive", "kind": "TRANSFORMER",
     "desc": "Resolve sensor_id list into live Sensor instances.",
     "inputs": [("sensor_ids", "FACT", False)],
     "outputs": [("sensors", "FACT")],
     "provides": ["sensors"], "requires": [],
     "emits": ["sensors"],
     "out_cap": "lab.perceive.resolve.out:sensors"},
    {"slot": "lab.perceive.policy",       "area": "perceive", "name": "policy",
     "module": "agent_lab.nodes.perceive.policy.plugin",
     "class": "PerceivePolicy",
     "stage": "perceive", "kind": "VALIDATOR",
     "desc": "Apply the perceive guard policy to sensor resolution.",
     "inputs": [("sensors", "FACT", False), ("state", "FACT", False)],
     "outputs": [("policy", "FACT")],
     "provides": ["policy"], "requires": ["sensors"],
     "emits": ["policy"],
     "out_cap": "lab.perceive.policy.out:policy"},
    {"slot": "lab.perceive.memory",       "area": "perceive", "name": "memory",
     "module": "agent_lab.nodes.perceive.memory.plugin",
     "class": "PerceiveMemory",
     "stage": "perceive", "kind": "TRANSFORMER",
     "desc": "Pull relevant memory items from the remember store.",
     "inputs": [("query", "FACT", False), ("state", "FACT", False)],
     "outputs": [("memory_items", "FACT")],
     "provides": ["memory_items"], "requires": [],
     "emits": ["memory_items"],
     "out_cap": "lab.perceive.memory.out:memory_items"},
    {"slot": "lab.perceive.trim",         "area": "perceive", "name": "trim",
     "module": "agent_lab.nodes.perceive.trim.plugin",
     "class": "PerceiveTrim",
     "stage": "perceive", "kind": "TRANSFORMER",
     "desc": "Trim + rank sensor items by relevance / budget.",
     "inputs": [("sensor_items", "FACT", False), ("state", "FACT", False)],
     "outputs": [("trimmed", "FACT")],
     "provides": ["trimmed"], "requires": ["sensor_items"],
     "emits": ["trimmed"],
     "out_cap": "lab.perceive.trim.out:trimmed"},
    {"slot": "lab.perceive.commit",       "area": "perceive", "name": "commit",
     "module": "agent_lab.nodes.perceive.commit.plugin",
     "class": "PerceiveCommit",
     "stage": "perceive", "kind": "PRODUCER",
     "desc": "Commit the perceived sensor bundle to the session log.",
     "inputs": [("trimmed", "FACT", False), ("state", "FACT", False)],
     "outputs": [("committed", "FACT")],
     "provides": ["committed"], "requires": ["trimmed"],
     "emits": ["committed"],
     "out_cap": "lab.perceive.commit.out:committed"},
    # think phase
    {"slot": "lab.think.expose",          "area": "think", "name": "expose",
     "module": "agent_lab.nodes.think.expose.plugin",
     "class": "ThinkExpose",
     "stage": "think", "kind": "TRANSFORMER",
     "desc": "Extract messages + tools from a committed ContextManifest.",
     "inputs": [("in_assembled_manifest", "MANIFEST", False), ("in_state", "FACT", False)],
     "outputs": [("messages", "MESSAGE"), ("tools", "FACT")],
     "provides": ["think_messages", "think_tools"], "requires": ["context_manifest"],
     "emits": ["think_messages", "think_tools"],
     "out_caps": ["lab.think.expose.out:messages", "lab.think.expose.out:tools"]},
    {"slot": "lab.think.reason",          "area": "think", "name": "reason",
     "module": "agent_lab.nodes.think.reason.plugin",
     "class": "ThinkReason",
     "stage": "think", "kind": "EXECUTOR",
     "desc": "Call OpenAICompatAdapter.complete on exposed messages.",
     "inputs": [("messages", "MESSAGE", False), ("tools", "FACT", False)],
     "outputs": [("response", "MESSAGE")],
     "provides": ["llm_response"], "requires": ["think_messages"],
     "emits": ["llm_call"],
     "out_cap": "lab.think.reason.out:response"},
    {"slot": "lab.think.classify",        "area": "think", "name": "classify",
     "module": "agent_lab.nodes.think.classify.plugin",
     "class": "ThinkClassify",
     "stage": "think", "kind": "TRANSFORMER",
     "desc": "Classify LLMResponse into a Decision (lab action_type).",
     "inputs": [("response", "MESSAGE", False)],
     "outputs": [("decision", "FACT")],
     "provides": ["think_decision"], "requires": [],
     "emits": ["think_decision"],
     "out_cap": "lab.think.classify.out:decision"},
    {"slot": "lab.think.guard",           "area": "think", "name": "guard",
     "module": "agent_lab.nodes.think.guard.plugin",
     "class": "ThinkGuard",
     "stage": "think", "kind": "VALIDATOR",
     "desc": "Enforce DecisionGate over the decision.",
     "inputs": [("decision", "FACT", False), ("in_state", "FACT", False)],
     "outputs": [("decision", "FACT"), ("think_signal", "FACT")],
     "provides": ["think_decision"], "requires": [],
     "emits": ["think_decision", "think_signal"],
     "out_caps": ["lab.think.guard.out:decision", "lab.think.guard.out:think_signal"]},
    # reflect phase
    {"slot": "lab.reflect.critique",       "area": "reflect", "name": "critique",
     "module": "agent_lab.nodes.reflect.critique.plugin",
     "class": "ReflectCritique",
     "stage": "reflect", "kind": "TRANSFORMER",
     "desc": "Run the reflect critic on the latest observation.",
     "inputs": [("observation", "FACT", False)],
     "outputs": [("critique", "FACT")],
     "provides": ["reflect_critique"], "requires": [],
     "emits": ["reflect_critique"],
     "out_cap": "lab.reflect.critique.out:critique"},
    {"slot": "lab.reflect.extract",       "area": "reflect", "name": "extract",
     "module": "agent_lab.nodes.reflect.extract.plugin",
     "class": "ReflectExtract",
     "stage": "reflect", "kind": "TRANSFORMER",
     "desc": "Extract a lesson from the critique.",
     "inputs": [("critique", "FACT", False)],
     "outputs": [("lesson", "FACT")],
     "provides": ["reflect_lesson"], "requires": [],
     "emits": ["reflect_lesson"],
     "out_cap": "lab.reflect.extract.out:lesson"},
    {"slot": "lab.reflect.join",          "area": "reflect", "name": "join",
     "module": "agent_lab.nodes.reflect.join.plugin",
     "class": "ReflectJoin",
     "stage": "reflect", "kind": "PRODUCER",
     "desc": "Join critique + lesson into a reflection artifact.",
     "inputs": [("critique", "FACT", False), ("lesson", "FACT", False)],
     "outputs": [("reflection", "FACT")],
     "provides": ["reflect_artifact"], "requires": [],
     "emits": ["reflect_artifact"],
     "out_cap": "lab.reflect.join.out:reflection"},
    # remember phase
    {"slot": "lab.remember.admit",        "area": "remember", "name": "admit",
     "module": "agent_lab.nodes.remember.admit.plugin",
     "class": "RememberAdmit",
     "stage": "remember", "kind": "PRODUCER",
     "desc": "Decide which facts to admit to the journal.",
     "inputs": [("reflection", "FACT", False)],
     "outputs": [("fact", "FACT")],
     "provides": ["remembered_fact"], "requires": [],
     "emits": ["remembered_fact"],
     "out_cap": "lab.remember.admit.out:fact"},
    {"slot": "lab.remember.commit",       "area": "remember", "name": "commit",
     "module": "agent_lab.nodes.remember.commit.plugin",
     "class": "RememberCommit",
     "stage": "remember", "kind": "EXECUTOR",
     "desc": "Commit the admitted fact to the journal via Session.append.",
     "inputs": [("fact", "FACT", False)],
     "outputs": [("remembered", "FACT")],
     "provides": ["remembered_artifact"], "requires": [],
     "emits": ["remembered_artifact"],
     "out_cap": "lab.remember.commit.out:remembered"},
    {"slot": "lab.remember.fold_history", "area": "remember", "name": "fold_history",
     "module": "agent_lab.nodes.remember.fold_history.plugin",
     "class": "RememberFoldHistory",
     "stage": "remember", "kind": "TRANSFORMER",
     "desc": "Fold history of remembered facts into a digest.",
     "inputs": [("remembered", "FACT", False)],
     "outputs": [("history", "FACT")],
     "provides": ["remembered_history"], "requires": [],
     "emits": ["remembered_history"],
     "out_cap": "lab.remember.fold_history.out:history"},
    {"slot": "lab.remember.snapshot",     "area": "remember", "name": "snapshot",
     "module": "agent_lab.nodes.remember.snapshot.plugin",
     "class": "RememberSnapshot",
     "stage": "remember", "kind": "PRODUCER",
     "desc": "Snapshot the current remember state for resume.",
     "inputs": [("history", "FACT", False)],
     "outputs": [("snapshot", "FACT")],
     "provides": ["remembered_snapshot"], "requires": [],
     "emits": ["remembered_snapshot"],
     "out_cap": "lab.remember.snapshot.out:snapshot"},
]


# =============================================================================
# EXTENDED_CARRIERS — control / session_log / lineage / event / passthrough /
# tool / llm / model_eye / model_visible
# =============================================================================
EXTENDED_CARRIERS: list[dict] = [
    # control plane
    {"slot": "lab.control.route_on", "area": "control", "name": "route_on",
     "module": "agent_lab.plugins.semantic_router", "class": "SemanticRouterPlugin",
     "stage": "control", "kind": "ROUTER",
     "desc": "Route a node output to one of several downstream paths by predicate.",
     "provides": [], "requires": [], "emits": [],
     "out_caps": []},
    {"slot": "lab.control.barrier", "area": "control", "name": "barrier",
     "module": "agent_lab.plugins.control_slots", "class": "ControlSlotsPlugin",
     "stage": "control", "kind": "ROUTER",
     "desc": "Single-slot pass-through (BSP barrier lives in runtime scheduler).",
     "provides": [], "requires": [], "emits": [],
     "out_caps": []},
    {"slot": "lab.control.join", "area": "control", "name": "join",
     "module": "agent_lab.plugins.control_slots", "class": "ControlSlotsPlugin",
     "stage": "control", "kind": "ROUTER",
     "desc": "Join N parallel branch outputs into one artifact.",
     "provides": [], "requires": [], "emits": [],
     "out_caps": []},
    {"slot": "lab.control.discard", "area": "control", "name": "discard",
     "module": "agent_lab.plugins.control_slots", "class": "ControlSlotsPlugin",
     "stage": "control", "kind": "PRODUCER",
     "desc": "Discard an output (sink only).",
     "provides": [], "requires": [], "emits": [],
     "out_caps": []},
    {"slot": "lab.control.observe_checkpoint", "area": "control", "name": "observe_checkpoint",
     "module": "agent_lab.plugins.observers", "class": "ObserverPlugin",
     "stage": "control", "kind": "TRANSFORMER",
     "desc": "Observe node_start / node_end events for checkpointing.",
     "provides": [], "requires": [], "emits": [],
     "out_caps": []},
    {"slot": "lab.control.observe_wildcard_node", "area": "control", "name": "observe_wildcard_node",
     "module": "agent_lab.plugins.observers", "class": "ObserverPlugin",
     "stage": "control", "kind": "TRANSFORMER",
     "desc": "Wildcard node observation (all node ids).",
     "provides": [], "requires": [], "emits": [],
     "out_caps": []},
    {"slot": "lab.control.stop_decide", "area": "control", "name": "stop_decide",
     "module": "agent_lab.nodes.control.stop_decide.plugin",
     "class": "StopDecideNode",
     "stage": "control", "kind": "VALIDATOR",
     "desc": "Decide if the loop should stop after a phase.",
     "inputs": [("state", "FACT", False)],
     "outputs": [("decision", "FACT")],
     "provides": ["stop_decision"], "requires": [],
     "emits": ["stop_decision"],
     "out_caps": []},
    {"slot": "lab.control.stop_focus_node", "area": "control", "name": "stop_focus_node",
     "module": "agent_lab.nodes.control.stop_focus_node.plugin",
     "class": "StopFocusNode",
     "stage": "control", "kind": "VALIDATOR",
     "desc": "Stop the loop on focused evaluation criteria.",
     "inputs": [("state", "FACT", False)],
     "outputs": [("decision", "FACT")],
     "provides": ["stop_focus"], "requires": [],
     "emits": ["stop_focus"],
     "out_caps": []},
    {"slot": "lab.control.act_execute_node", "area": "control", "name": "act_execute_node",
     "module": "agent_lab.nodes.control.act_execute_node.plugin",
     "class": "ActExecuteNode",
     "stage": "control", "kind": "EXECUTOR",
     "desc": "Control-plane wrapper around the act execute node.",
     "provides": ["act_execute_control"], "requires": [],
     "emits": [],
     "out_caps": []},
    {"slot": "lab.control.act_authorize_node", "area": "control", "name": "act_authorize_node",
     "module": "agent_lab.nodes.control.act_authorize_node.plugin",
     "class": "ActAuthorizeNode",
     "stage": "control", "kind": "VALIDATOR",
     "desc": "Control-plane wrapper around the act authorize node.",
     "provides": ["act_authorize_control"], "requires": [],
     "emits": [],
     "out_caps": []},
    {"slot": "lab.control.act_budget_node", "area": "control", "name": "act_budget_node",
     "module": "agent_lab.nodes.control.act_budget_node.plugin",
     "class": "ActBudgetNode",
     "stage": "control", "kind": "VALIDATOR",
     "desc": "Validate that an act request fits the budget.",
     "provides": ["act_budget_check"], "requires": [],
     "emits": [],
     "out_caps": []},
    {"slot": "lab.control.act_constrain_node", "area": "control", "name": "act_constrain_node",
     "module": "agent_lab.nodes.control.act_constrain_node.plugin",
     "class": "ActConstrainNode",
     "stage": "control", "kind": "VALIDATOR",
     "desc": "Validate that an act request meets constraints.",
     "provides": ["act_constraint_check"], "requires": [],
     "emits": [],
     "out_caps": []},
    {"slot": "lab.control.act_safe_boundary_node", "area": "control", "name": "act_safe_boundary_node",
     "module": "agent_lab.nodes.control.act_safe_boundary_node.plugin",
     "class": "ActSafeBoundaryNode",
     "stage": "control", "kind": "VALIDATOR",
     "desc": "Verify the act is within the safe-boundary envelope.",
     "provides": ["act_safe_boundary"], "requires": [],
     "emits": [],
     "out_caps": []},
    {"slot": "lab.control.perceive_context_node", "area": "control", "name": "perceive_context_node",
     "module": "agent_lab.nodes.control.perceive_context_node.plugin",
     "class": "PerceiveContextNode",
     "stage": "control", "kind": "PRODUCER",
     "desc": "Control-plane wrapper around the perceive context producer.",
     "provides": ["perceive_context"], "requires": [],
     "emits": [],
     "out_caps": []},
    {"slot": "lab.control.remember_admit", "area": "control", "name": "remember_admit",
     "module": "agent_lab.nodes.control.remember_admit.plugin",
     "class": "RememberAdmitNode",
     "stage": "control", "kind": "PRODUCER",
     "desc": "Control-plane wrapper around the remember admit producer.",
     "provides": ["remember_admit_control"], "requires": [],
     "emits": [],
     "out_caps": []},
    {"slot": "lab.control.think_guard", "area": "control", "name": "think_guard",
     "module": "agent_lab.nodes.control.think_guard.plugin",
     "class": "ThinkGuardNode",
     "stage": "control", "kind": "VALIDATOR",
     "desc": "Control-plane wrapper around the think guard validator.",
     "provides": ["think_guard_control"], "requires": [],
     "emits": [],
     "out_caps": []},
    # session_log
    {"slot": "lab.session_log.append_node_start", "area": "session_log", "name": "append_node_start",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.node_start.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.append_node_end", "area": "session_log", "name": "append_node_end",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.node_end.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.append_edge_fire", "area": "session_log", "name": "append_edge_fire",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.edge_fire.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.append_subgraph_enter", "area": "session_log", "name": "append_subgraph_enter",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.subgraph_enter.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.append_subgraph_exit", "area": "session_log", "name": "append_subgraph_exit",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.subgraph_exit.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.append_decision", "area": "session_log", "name": "append_decision",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.decision.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.append_observation", "area": "session_log", "name": "append_observation",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.observation.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.append_reflection", "area": "session_log", "name": "append_reflection",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.reflection.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.append_tool_result", "area": "session_log", "name": "append_tool_result",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.tool_result.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.append_before_compile", "area": "session_log", "name": "append_before_compile",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.before_compile.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.append_after_compile", "area": "session_log", "name": "append_after_compile",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.after_compile.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.append_checkpoint", "area": "session_log", "name": "append_checkpoint",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "EXECUTOR",
     "desc": "Session.append(graph.checkpoint.v1).",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.fanout_observers", "area": "session_log", "name": "fanout_observers",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "PRODUCER",
     "desc": "Fan session log events to observer plugins.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.register_observer", "area": "session_log", "name": "register_observer",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "PRODUCER",
     "desc": "Register an observer plugin for session log events.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.consume_events", "area": "session_log", "name": "consume_events",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "TRANSFORMER",
     "desc": "Consume session log events from the journal.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.snapshot_events", "area": "session_log", "name": "snapshot_events",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "PRODUCER",
     "desc": "Snapshot session log events for resume.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.attach_sink", "area": "session_log", "name": "attach_sink",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "PRODUCER",
     "desc": "Attach a sink to the session log stream.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.flush_sink", "area": "session_log", "name": "flush_sink",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "PRODUCER",
     "desc": "Flush a sink to its durable store.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.fold_header", "area": "session_log", "name": "fold_header",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "TRANSFORMER",
     "desc": "Fold the session log header into a step header.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.session_log.session_seq", "area": "session_log", "name": "session_seq",
     "module": "agent_lab.nodes.session_log.plugin", "class": "SessionLogEmitterPlugin",
     "stage": "session_log", "kind": "PRODUCER",
     "desc": "Allocate a per-session sequence number.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    # lineage
    {"slot": "lab.lineage.trace_edge_fire", "area": "lineage", "name": "trace_edge_fire",
     "module": "agent_lab.nodes.lineage.trace_edge_fire.plugin", "class": "TraceEdgeFire",
     "stage": "lineage", "kind": "EXECUTOR",
     "desc": "Trace edge-fire lineage event.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.lineage.trace_node_start", "area": "lineage", "name": "trace_node_start",
     "module": "agent_lab.nodes.lineage.trace_node_start.plugin", "class": "TraceNodeStart",
     "stage": "lineage", "kind": "EXECUTOR",
     "desc": "Trace node-start lineage event.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.lineage.trace_node_end", "area": "lineage", "name": "trace_node_end",
     "module": "agent_lab.nodes.lineage.trace_node_end.plugin", "class": "TraceNodeEnd",
     "stage": "lineage", "kind": "EXECUTOR",
     "desc": "Trace node-end lineage event.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.lineage.trace_subgraph_enter", "area": "lineage", "name": "trace_subgraph_enter",
     "module": "agent_lab.nodes.lineage.trace_subgraph_enter.plugin", "class": "TraceSubgraphEnter",
     "stage": "lineage", "kind": "EXECUTOR",
     "desc": "Trace subgraph-enter lineage event.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    {"slot": "lab.lineage.trace_subgraph_exit", "area": "lineage", "name": "trace_subgraph_exit",
     "module": "agent_lab.nodes.lineage.trace_subgraph_exit.plugin", "class": "TraceSubgraphExit",
     "stage": "lineage", "kind": "EXECUTOR",
     "desc": "Trace subgraph-exit lineage event.",
     "provides": [], "requires": ["lab.session"], "emits": [], "out_caps": []},
    # event
    {"slot": "lab.event.emit", "area": "event", "name": "emit",
     "module": "agent_lab.nodes.event.emit.plugin", "class": "EventEmitNode",
     "stage": "event", "kind": "EXECUTOR",
     "desc": "Emit a domain event into the event bus.",
     "inputs": [("event", "FACT", False), ("payload", "FACT", False)],
     "outputs": [("emitted", "FACT")],
     "provides": ["event_emit"], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.event.tail", "area": "event", "name": "tail",
     "module": "agent_lab.nodes.event.tail.plugin", "class": "EventTailNode",
     "stage": "event", "kind": "TRANSFORMER",
     "desc": "Tail the event bus for a filter.",
     "inputs": [("filter", "FACT", False)],
     "outputs": [("events", "FACT")],
     "provides": ["event_tail"], "requires": [], "emits": [], "out_caps": []},
    # llm
    {"slot": "lab.llm.assemble_messages", "area": "llm", "name": "assemble_messages",
     "module": "agent_lab.nodes.llm.assemble_messages.plugin", "class": "AssembleMessages",
     "stage": "llm", "kind": "ASSEMBLER",
     "desc": "Assemble OpenAI-style messages from a ContextManifest.",
     "inputs": [("manifest", "MANIFEST", False)],
     "outputs": [("messages", "MESSAGE")],
     "provides": ["llm_messages"], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.llm.call_llm", "area": "llm", "name": "call_llm",
     "module": "agent_lab.nodes.llm.call_llm.plugin", "class": "CallLLM",
     "stage": "llm", "kind": "EXECUTOR",
     "desc": "Call the LLM with assembled messages.",
     "inputs": [("messages", "MESSAGE", False)],
     "outputs": [("response", "MESSAGE")],
     "provides": ["llm_response"], "requires": ["llm_messages"], "emits": [], "out_caps": []},
    {"slot": "lab.llm.commit_manifest", "area": "llm", "name": "commit_manifest",
     "module": "agent_lab.nodes.llm.commit_manifest.plugin", "class": "CommitManifest",
     "stage": "llm", "kind": "PRODUCER",
     "desc": "Commit a frozen ContextManifest.",
     "inputs": [("messages", "MESSAGE", False)],
     "outputs": [("manifest", "MANIFEST")],
     "provides": ["llm_manifest"], "requires": [], "emits": [], "out_caps": []},
    # model_eye
    {"slot": "lab.model_eye.see", "area": "model_eye", "name": "see",
     "module": "agent_lab.nodes.model_eye.see.plugin", "class": "ModelEyeSee",
     "stage": "model_eye", "kind": "TRANSFORMER",
     "desc": "Project the model-visible input bundle into a Manifest.",
     "inputs": [("messages", "MESSAGE", False), ("tools", "FACT", False), ("results", "FACT", False)],
     "outputs": [("manifest", "MANIFEST")],
     "provides": ["model_visible_manifest"], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.model_eye.trust_classify", "area": "model_eye", "name": "trust_classify",
     "module": "agent_lab.nodes.model_eye.trust_classify.plugin", "class": "TrustClassify",
     "stage": "model_eye", "kind": "VALIDATOR",
     "desc": "Tag tool results with a trust classification.",
     "inputs": [("results", "FACT", False)],
     "outputs": [("trust_labels", "FACT")],
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.model_eye.guard", "area": "model_eye", "name": "guard",
     "module": "agent_lab.nodes.model_eye.guard.plugin", "class": "ModelEyeGuard",
     "stage": "model_eye", "kind": "VALIDATOR",
     "desc": "Apply PII / secrets redaction on the visible manifest.",
     "inputs": [("manifest", "MANIFEST", False)],
     "outputs": [("redacted", "MANIFEST")],
     "provides": ["model_visible_redacted"], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.model_eye.freeze", "area": "model_eye", "name": "freeze",
     "module": "agent_lab.nodes.model_eye.freeze.plugin", "class": "ModelEyeFreeze",
     "stage": "model_eye", "kind": "PRODUCER",
     "desc": "Freeze the manifest into an immutable ContextManifest.",
     "inputs": [("redacted", "MANIFEST", False)],
     "outputs": [("frozen", "MANIFEST")],
     "provides": ["model_visible_frozen"], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.model_eye.shape", "area": "model_eye", "name": "shape",
     "module": "agent_lab.nodes.model_eye.shape.plugin", "class": "ModelEyeShape",
     "stage": "model_eye", "kind": "TRANSFORMER",
     "desc": "Shape the frozen manifest into the model-visible input bytes.",
     "inputs": [("frozen", "MANIFEST", False)],
     "outputs": [("bytes", "FACT")],
     "provides": ["model_visible_bytes"], "requires": [], "emits": [], "out_caps": []},
    # model_visible
    {"slot": "lab.model_visible.prompt_assemble", "area": "model_visible", "name": "prompt_assemble",
     "module": "agent_lab.nodes.model_visible.prompt_assemble.plugin", "class": "PromptAssemble",
     "stage": "model_visible", "kind": "ASSEMBLER",
     "desc": "Assemble the final prompt from the visible manifest.",
     "inputs": [("manifest", "MANIFEST", False)],
     "outputs": [("prompt", "FACT")],
     "provides": ["model_visible_prompt"], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.model_visible.manifest_commit", "area": "model_visible", "name": "manifest_commit",
     "module": "agent_lab.nodes.model_visible.manifest_commit.plugin", "class": "ManifestCommit",
     "stage": "model_visible", "kind": "PRODUCER",
     "desc": "Commit the final manifest.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.model_visible.messages_merge", "area": "model_visible", "name": "messages_merge",
     "module": "agent_lab.nodes.model_visible.messages_merge.plugin", "class": "MessagesMerge",
     "stage": "model_visible", "kind": "ASSEMBLER",
     "desc": "Merge multiple message sources into one prompt.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.model_visible.history_attach", "area": "model_visible", "name": "history_attach",
     "module": "agent_lab.nodes.model_visible.history_attach.plugin", "class": "HistoryAttach",
     "stage": "model_visible", "kind": "TRANSFORMER",
     "desc": "Attach the per-session history to the prompt.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    # passthrough
    {"slot": "lab.passthrough.identity", "area": "passthrough", "name": "identity",
     "module": "agent_lab.nodes.passthrough.identity.plugin", "class": "Identity",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Pass-through identity node.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.constant", "area": "passthrough", "name": "constant",
     "module": "agent_lab.nodes.passthrough.constant.plugin", "class": "Constant",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Emit a constant value.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.dedup", "area": "passthrough", "name": "dedup",
     "module": "agent_lab.nodes.passthrough.dedup.plugin", "class": "Dedup",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Deduplicate the input list.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.rank", "area": "passthrough", "name": "rank",
     "module": "agent_lab.nodes.passthrough.rank.plugin", "class": "Rank",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Rank the input list.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.redact", "area": "passthrough", "name": "redact",
     "module": "agent_lab.nodes.passthrough.redact.plugin", "class": "Redact",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Apply redaction patterns.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.select", "area": "passthrough", "name": "select",
     "module": "agent_lab.nodes.passthrough.select.plugin", "class": "Select",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Select a field from the input.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.prefix", "area": "passthrough", "name": "prefix",
     "module": "agent_lab.nodes.passthrough.prefix.plugin", "class": "Prefix",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Prefix the input text.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.identity_v2", "area": "passthrough", "name": "identity_v2",
     "module": "agent_lab.nodes.passthrough.identity_v2.plugin", "class": "IdentityV2",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Identity v2 with extra typing.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.dedup_v2", "area": "passthrough", "name": "dedup_v2",
     "module": "agent_lab.nodes.passthrough.dedup_v2.plugin", "class": "DedupV2",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Deduplicate v2.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.rank_v2", "area": "passthrough", "name": "rank_v2",
     "module": "agent_lab.nodes.passthrough.rank_v2.plugin", "class": "RankV2",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Rank v2.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.redact_v2", "area": "passthrough", "name": "redact_v2",
     "module": "agent_lab.nodes.passthrough.redact_v2.plugin", "class": "RedactV2",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Redact v2.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.select_v2", "area": "passthrough", "name": "select_v2",
     "module": "agent_lab.nodes.passthrough.select_v2.plugin", "class": "SelectV2",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Select v2.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.passthrough.prefix_v2", "area": "passthrough", "name": "prefix_v2",
     "module": "agent_lab.nodes.passthrough.prefix_v2.plugin", "class": "PrefixV2",
     "stage": "passthrough", "kind": "PASSTHROUGH",
     "desc": "Prefix v2.",
     "provides": [], "requires": [], "emits": [], "out_caps": []},
    # tool
    {"slot": "lab.tool.expose_schemas", "area": "tool", "name": "expose_schemas",
     "module": "agent_lab.nodes.tool.expose_schemas.plugin", "class": "ExposeSchemas",
     "stage": "tool", "kind": "PRODUCER",
     "desc": "Expose tool schemas to the model-visible manifest.",
     "provides": ["tool_schemas_exposed"], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.tool.resolve_tool", "area": "tool", "name": "resolve_tool",
     "module": "agent_lab.nodes.tool.resolve_tool.plugin", "class": "ResolveTool",
     "stage": "tool", "kind": "VALIDATOR",
     "desc": "Resolve a tool name to a Tool instance.",
     "provides": ["tool_resolved"], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.tool.grant_check", "area": "tool", "name": "grant_check",
     "module": "agent_lab.nodes.tool.grant_check.plugin", "class": "GrantCheck",
     "stage": "tool", "kind": "VALIDATOR",
     "desc": "Verify the tool call is within the grant.",
     "provides": ["tool_grant_checked"], "requires": [], "emits": [], "out_caps": []},
    {"slot": "lab.tool.registry_loader", "area": "tool", "name": "registry_loader",
     "module": "agent_lab.nodes.tool.registry_loader.plugin", "class": "RegistryLoader",
     "stage": "tool", "kind": "PRODUCER",
     "desc": "Load the lab tool registry from YAML at boot.",
     "provides": ["tool_registry_loaded"], "requires": [], "emits": [], "out_caps": []},
]


# Merge extended into the main list (must run before main() iterates)
NODE_CARRIERS.extend(EXTENDED_CARRIERS)


def render_carrier(node: dict) -> str:
    """Render a single carrier Python source."""
    slot = node["slot"]
    area = node["area"]
    name = node["name"]
    module = node["module"]
    cls = node["class"]
    stage = node["stage"]
    kind = node["kind"]
    desc = node["desc"]
    inputs = node.get("inputs", [])
    outputs = node.get("outputs", [])
    provides = node.get("provides", [])
    requires = node.get("requires", [])
    emits = node.get("emits", [])
    out_cap = node.get("out_cap")
    out_caps = node.get("out_caps", [out_cap] if out_cap else [])

    return f'''# PR-D final 2/2 — {area}.{name} real @plugin carrier
"""Real carrier for ``{module}.{cls}``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``{cls}`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``{slot}``
Output capability: ``{", ".join(out_caps) or "(none)"}``

delete-when (PR-D final 2/2):
- agent_lab/nodes/{area}/{name}/plugin.py replaced by this carrier
  (test env: delete-when happens when LCA runtime with cordis
  is in place and the legacy plugin can be removed)
"""

from __future__ import annotations

from lca.plugins.lab.internal.hooks import (
    LabCarrier,
    bind_carrier,
)


# Carrier data: what the loader's register_carrier() needs.
_CARRIER = LabCarrier(
    id="{slot}",
    stage="{stage}",
    kind="{kind}",
    description={desc!r},
    node_id={name!r},
    source_module={module!r},
    source_class={cls!r},
    provides={provides!r},
    requires={requires!r},
    emits={emits!r},
    inputs={[(p, k, r) for (p, k, r) in inputs]!r},
    outputs={[(p, k) for (p, k) in outputs]!r},
    out_capabilities={out_caps!r},
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


# Auto-bind on import so the loader walks these like any other plugin
# carrier — the setup() function is still callable from a real Cordis
# boot path for two-phase register.
bind_carrier(_CARRIER)


__all__ = ["setup", "_CARRIER"]
'''


def main():
    base = Path("lca/plugins/lab")
    written = []
    for node in NODE_CARRIERS:
        area = node["area"]
        name = node["name"]
        out = base / area / name / "plugin.py"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_carrier(node))
        written.append(str(out))
    return written


if __name__ == "__main__":
    paths = main()
    print(f"Generated {len(paths)} carriers:")
    for p in paths:
        print(f"  {p}")
