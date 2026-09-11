"""Port name closed set — typed contract for node-level data flow.

Per ADR-0219 §5: every port name written or read by a subgraph node must
appear here. Names not in this set are forbidden at the ``PortRegistry``
boundary (typed entry) and rejected at the Pydantic ``NodeOutput`` gate.

D5 mapping (each port name has one or more D4 consumers):

- ``decision``              think.classify / think.gate  →  outer interpreter / act phase
- ``observation``           observation nodes           →  outer interpreter
- ``reflection``            reflect nodes               →  outer interpreter
- ``response``              think.reason.complete       →  think.classify
- ``turn_plan``             think.reason.plan           →  think.reason.render
- ``turn_render``           think.reason.render         →  think.reason.complete
- ``in_assembled_manifest`` think.shortcut / think.route →  outer loop
- ``route_choice``          think.route                 →  downstream
- ``enforced_state``        think.route                 →  Reducer / state fold
- ``tool_calls``            decision.parse.tool_calls   →  decision.compose.action
- ``delegations``           decision.parse.tool_calls   →  decision.compose.action
- ``enforced_decision``     decision.enforce.chain_run  →  act subgraph
- ``intent``                decision.parse.intent       →  decision.compose.action
- ``role``                  role_snapshot.normalize     →  role_snapshot.compose
- ``role_snapshot``         role_snapshot.compose       →  downstream
- ``context``               context_compose.skills      →  think.reason.render
- ``manifest``              context_compose.collect     →  think.reason.render
- ``context_items``         perceive_turn.fold          →  perceive consumers
- ``raw_inputs``            perceive_turn.collect       →  perceive consumers
- ``prompt_text``           prompt_render.fill          →  prompt consumers
- ``prompt_trace``          prompt_render.fill          →  prompt consumers
- ``prompt_template``       prompt_render.assemble      →  prompt consumers
- ``render``                prompt_render.compile       →  prompt consumers
- ``template_selection``    template_select.pick        →  reasoner
- ``scored``                template_select.score       →  template_select.pick
- ``candidates``            template_select.enumerate   →  template_select.score
- ``forked_tools``          tool_fork.dispatch          →  act subgraph
- ``envelope``              act_subgraph.act_envelope   →  body / executor
- ``receipt``               effect_execute.execute      →  downstream
- ``memory_receipt``        memory_write.admit_policy / memory_write.dispatch → downstream
- ``stop_decision``         stop.policy                 →  outer interpreter
- ``stop_payload``          stop.policy                 →  outer interpreter

Historical (deleted, no D4 consumer — see ADR-0219 §7.2):

- ``think_signal``          retired 2026-09-10 (was think.gate invented field)

Adding a new port name requires updating the D5 mapping table in
``docs/adr/0219-phase-graph-unification.md`` §5.1 alongside the code.
"""

from __future__ import annotations

from typing import Literal

PortName = Literal[
    "candidates",
    "context",
    "context_items",
    "decision",
    "delegations",
    "enforced_decision",
    "enforced_state",
    "envelope",
    "forked_tools",
    "in_assembled_manifest",
    "intent",
    "manifest",
    "memory_receipt",
    "observation",
    "observations",
    "prompt_template",
    "prompt_text",
    "prompt_trace",
    "raw_inputs",
    "receipt",
    "reflection",
    "render",
    "response",
    "role",
    "role_snapshot",
    "route_choice",
    "scored",
    "stop_decision",
    "stop_payload",
    "template_selection",
    "tool_calls",
    "turn_plan",
    "turn_render",
]

__all__ = ["PortName"]
