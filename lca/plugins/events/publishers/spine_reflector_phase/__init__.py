"""spine_reflector_phase — ADR-0181 PR-5。

phase 全迁（13 EP）：
- perceive.phase.fold / phase.perceive.fold
- phase.think / phase.gate / phase.remember / phase.stop / phase.reflect.fold
- phase.act.fold.start / .end / phase.act.fold
- phase.tool.call.start / .end / phase.tool.denied
"""

from lca.plugins.events.publishers.spine_reflector_phase.plugin import (
    ReflectorClass,
    emit_perceive_phase_fold,
    emit_phase_act_fold,
    emit_phase_act_fold_end,
    emit_phase_act_fold_start,
    emit_phase_gate_fold,
    emit_phase_perceive_fold,
    emit_phase_reflect_fold,
    emit_phase_remember_fold,
    emit_phase_stop_fold,
    emit_phase_think_fold,
    emit_phase_tool_call_end,
    emit_phase_tool_call_start,
    emit_phase_tool_denied,
)

__all__ = [
    "ReflectorClass",
    "emit_perceive_phase_fold",
    "emit_phase_act_fold",
    "emit_phase_act_fold_end",
    "emit_phase_act_fold_start",
    "emit_phase_gate_fold",
    "emit_phase_perceive_fold",
    "emit_phase_reflect_fold",
    "emit_phase_remember_fold",
    "emit_phase_stop_fold",
    "emit_phase_think_fold",
    "emit_phase_tool_call_end",
    "emit_phase_tool_call_start",
    "emit_phase_tool_denied",
]
