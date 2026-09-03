"""spine_reflector_body_llm — ADR-0181 PR-3。

body + llm 全迁：旧 lca/plugins/observability/spine/reflectors/body_llm.py
全部 9 emit + spine_reflector_runtime exception 3 emit（lifecycle.finally /
exception.caught / exception.finally），signature 严格对齐旧 reflector，
调用方零改动（仅 import 路径换到 lca.plugins.events.publishers.*）。
"""

from lca.plugins.events.publishers.spine_reflector_body_llm.plugin import (
    ReflectorClass,
    emit_body_sandbox_enter,
    emit_body_sandbox_exit,
    emit_body_tool_decision_end,
    emit_body_tool_decision_start,
    emit_body_tool_execute_end,
    emit_body_tool_execute_start,
    emit_body_tool_retry,
    emit_llm_call_end,
    emit_llm_call_start,
    emit_llm_stream_stall,
    emit_llm_stream_token,
)

__all__ = [
    "ReflectorClass",
    "emit_body_sandbox_enter",
    "emit_body_sandbox_exit",
    "emit_body_tool_decision_end",
    "emit_body_tool_decision_start",
    "emit_body_tool_execute_end",
    "emit_body_tool_execute_start",
    "emit_body_tool_retry",
    "emit_llm_call_end",
    "emit_llm_call_start",
    "emit_llm_stream_stall",
    "emit_llm_stream_token",
]
