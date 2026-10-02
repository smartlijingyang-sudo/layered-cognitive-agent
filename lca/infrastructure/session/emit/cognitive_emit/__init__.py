"""Gate / perceive / think Session fact production (ADR-0191 R2, ADR-0194 P1-06/14/15).

Single production seam for ``gate.decided.v1``, ``context.manifested.v1``, and
reasoner spine EPs (via ``publish_ep_bound``). All helpers no-op when no Session
is bound (tests / offline).

The implementation is split by event family:

- ``envelope``: shared Session-bound envelope primitives (FactGateway calls).
- ``gate_events``: gate.decided / context.manifested catalog emitters.
- ``reflection_events``: critic / synthesizer / skill_router / prompt_assembler /
  reasoner spine emitters + the reasoner spine envelope.
- ``tool_events``: act-subgraph tool-call spine EPs.
- ``step_events``: node-level phase step/fold spine EPs.
"""

from __future__ import annotations

from lca.infrastructure.session.emit.cognitive_emit.envelope import (
    append_catalog_bound as append_catalog_bound,
)
from lca.infrastructure.session.emit.cognitive_emit.envelope import (
    publish_ep_bound as publish_ep_bound,
)
from lca.infrastructure.session.emit.cognitive_emit.gate_events import (
    emit_context_manifested,
    emit_context_manifested_for_state,
    emit_gate_decided,
    emit_gate_decided_from_policy,
)
from lca.infrastructure.session.emit.cognitive_emit.reflection_events import (
    _emit_reasoner_meta_from_render as _emit_reasoner_meta_from_render,
)
from lca.infrastructure.session.emit.cognitive_emit.reflection_events import (
    emit_critic_eval_end_for_state,
    emit_critic_eval_start_for_state,
    emit_prompt_assembler_end_for_state,
    emit_prompt_assembler_start_for_state,
    emit_reasoner_reason_end_for_state,
    emit_reasoner_reason_start_for_state,
    emit_skill_router_route_for_state,
    emit_synthesizer_merge_for_state,
    run_reasoner_generate_thoughts_with_spine_facts,
)
from lca.infrastructure.session.emit.cognitive_emit.step_events import (
    emit_phase_graph_subgraph_enter_for_state,
    emit_phase_graph_subgraph_exit_for_state,
    emit_phase_perceive_fold_for_state,
    emit_phase_reflect_fold_for_state,
    emit_phase_remember_fold_for_state,
    emit_phase_stop_fold_for_state,
    emit_phase_think_fold_for_state,
    emit_terminal_commit_for_state,
)
from lca.infrastructure.session.emit.cognitive_emit.tool_events import (
    emit_body_tool_execute_end_for_state as emit_body_tool_execute_end_for_state,
)
from lca.infrastructure.session.emit.cognitive_emit.tool_events import (
    emit_body_tool_execute_start_for_state as emit_body_tool_execute_start_for_state,
)
from lca.infrastructure.session.emit.cognitive_emit.tool_events import (
    emit_phase_act_fold_end_for_state,
    emit_phase_act_fold_start_for_state,
    emit_phase_tool_call_end_for_state,
    emit_phase_tool_call_start_for_state,
    emit_think_gate_end_for_state,
    emit_think_gate_start_for_state,
)

__all__ = [
    "emit_context_manifested",
    "emit_context_manifested_for_state",
    "emit_critic_eval_end_for_state",
    "emit_critic_eval_start_for_state",
    "emit_gate_decided",
    "emit_gate_decided_from_policy",
    "emit_phase_act_fold_end_for_state",
    "emit_phase_act_fold_start_for_state",
    "emit_phase_graph_subgraph_enter_for_state",
    "emit_phase_graph_subgraph_exit_for_state",
    "emit_phase_perceive_fold_for_state",
    "emit_phase_reflect_fold_for_state",
    "emit_phase_remember_fold_for_state",
    "emit_phase_stop_fold_for_state",
    "emit_phase_think_fold_for_state",
    "emit_phase_tool_call_end_for_state",
    "emit_phase_tool_call_start_for_state",
    "emit_prompt_assembler_end_for_state",
    "emit_prompt_assembler_start_for_state",
    "emit_reasoner_reason_end_for_state",
    "emit_reasoner_reason_start_for_state",
    "emit_skill_router_route_for_state",
    "emit_synthesizer_merge_for_state",
    "emit_terminal_commit_for_state",
    "emit_think_gate_end_for_state",
    "emit_think_gate_start_for_state",
    "run_reasoner_generate_thoughts_with_spine_facts",
]
