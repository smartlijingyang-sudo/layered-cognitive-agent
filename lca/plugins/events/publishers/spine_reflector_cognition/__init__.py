"""spine_reflector_cognition — ADR-0181 试点 + PR-2 cognition 全迁。

PR-2：cognition 余 15 emit 全部下沉（signature 严格对齐旧
lca/plugins/observability/spine/reflectors/cognition.py 全部 16 emit，
调用方零改动）。
"""

from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
    ReflectorClass,
    emit_brain_gate_end,
    emit_brain_gate_start,
    emit_brain_perceive_end,
    emit_brain_perceive_start,
    emit_brain_think_end,
    emit_brain_think_start,
    emit_critic_eval_end,
    emit_critic_eval_start,
    emit_memory_read,
    emit_memory_write,
    emit_prompt_assembler_end,
    emit_prompt_assembler_start,
    emit_reasoner_reason_end,
    emit_reasoner_reason_start,
    emit_skill_router_route,
    emit_synthesizer_merge,
)

__all__ = [
    "ReflectorClass",
    "emit_brain_gate_end",
    "emit_brain_gate_start",
    "emit_brain_perceive_end",
    "emit_brain_perceive_start",
    "emit_brain_think_end",
    "emit_brain_think_start",
    "emit_critic_eval_end",
    "emit_critic_eval_start",
    "emit_memory_read",
    "emit_memory_write",
    "emit_prompt_assembler_end",
    "emit_prompt_assembler_start",
    "emit_reasoner_reason_end",
    "emit_reasoner_reason_start",
    "emit_skill_router_route",
    "emit_synthesizer_merge",
]
