"""spine_reflector_perception plugin（ADR-0181 PR-6 / ADR-0183 PR-7）。

PR-6：perception 维度 6 EP（新加，old manifest 没有）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.payloads import Category, SpineEventPayload

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef

log = logging.getLogger(__name__)


class ReflectorClass:
    """publisher plugin 类（空标记类）。机制按 class 全路径鉴权。"""


def _send(
    *,
    category: str,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> EventRef:
    from lca_kernel.events.bus import EventBus

    sp = SpineEventPayload(
        category=Category(category),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventBus.default().publish(sp, producer=ReflectorClass)


def emit_perception_observe(*, run_id: str, source: str) -> EventRef:
    return _send(
        category="spine.perception.observe",
        execution_point="perception.observe",
        channel="fact",
        payload={"run_id": run_id, "source": source},
    )


def emit_attention_focus(*, run_id: str, target: str) -> EventRef:
    return _send(
        category="spine.perception.attention.focus",
        execution_point="attention.focus",
        channel="fact",
        payload={"run_id": run_id, "target": target},
    )


def emit_attention_blur(*, run_id: str, target: str) -> EventRef:
    return _send(
        category="spine.perception.attention.blur",
        execution_point="attention.blur",
        channel="fact",
        payload={"run_id": run_id, "target": target},
    )


def emit_perception_signal_detected(
    *,
    run_id: str,
    signal_kind: str,
    score: float,
) -> EventRef:
    return _send(
        category="spine.perception.signal.detected",
        execution_point="perception.signal.detected",
        channel="fact",
        payload={"run_id": run_id, "signal_kind": signal_kind, "score": score},
    )


def emit_perception_fused(
    *,
    run_id: str,
    artifact_id: str,
    sources: list[str],
) -> EventRef:
    return _send(
        category="spine.perception.fused",
        execution_point="perception.fused",
        channel="fact",
        payload={
            "run_id": run_id,
            "artifact_id": artifact_id,
            "sources": sources,
        },
    )


def emit_perception_artifact_built(
    *,
    run_id: str,
    artifact_id: str,
    size_bytes: int,
) -> EventRef:
    return _send(
        category="spine.perception.artifact.built",
        execution_point="perception.artifact.built",
        channel="fact",
        payload={
            "run_id": run_id,
            "artifact_id": artifact_id,
            "size_bytes": size_bytes,
        },
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
