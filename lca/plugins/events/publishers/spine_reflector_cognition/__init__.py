"""spine_reflector_cognition — 试点 EP 1 个 publisher（ADR-0181 试点）。

试点 publisher：迁 ``lca/plugins/observability/spine/reflectors/cognition.py``
的 ``emit_brain_perceive_start`` 一行；其余 39 emit 留给 PR-2。

业务方调：
    EventMechanism.send(
        SpineEventPayload(execution_point="brain.perceive.start", ...),
        plugin=ReflectorClass,
    )
"""

from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
    ReflectorClass,
    emit_brain_perceive_start,
)

__all__ = ["ReflectorClass", "emit_brain_perceive_start"]
