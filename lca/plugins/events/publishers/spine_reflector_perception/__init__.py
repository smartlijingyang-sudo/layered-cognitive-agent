"""spine_reflector_perception — ADR-0181 PR-6。

perception 维度 6 EP（新加，PR-6）：
- perception.observe / attention.focus / attention.blur
- perception.signal.detected / perception.fused
- perception.artifact.built
"""

from lca.plugins.events.publishers.spine_reflector_perception.plugin import (
    ReflectorClass,
    emit_attention_blur,
    emit_attention_focus,
    emit_perception_artifact_built,
    emit_perception_fused,
    emit_perception_observe,
    emit_perception_signal_detected,
)

__all__ = [
    "ReflectorClass",
    "emit_attention_blur",
    "emit_attention_focus",
    "emit_perception_artifact_built",
    "emit_perception_fused",
    "emit_perception_observe",
    "emit_perception_signal_detected",
]
