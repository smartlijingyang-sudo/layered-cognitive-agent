"""spine_reflector_agent_spawn — ADR-0181 PR-4。

agent_loop + agent 全迁（5 EP）：
- agent_loop.iteration.start / .end
- agent.spawn / agent.iteration / agent.final

签名严格对齐旧 lca/plugins/observability/spine/reflectors/agent_spawn.py
调用方零改动。
"""

from lca.plugins.events.publishers.spine_reflector_agent_spawn.plugin import (
    ReflectorClass,
    emit_agent_final,
    emit_agent_iteration,
    emit_agent_loop_iteration_end,
    emit_agent_loop_iteration_start,
    emit_agent_spawn,
)

__all__ = [
    "ReflectorClass",
    "emit_agent_final",
    "emit_agent_iteration",
    "emit_agent_loop_iteration_end",
    "emit_agent_loop_iteration_start",
    "emit_agent_spawn",
]
