# act.observe — Observation → manifest(single exit from act phase)。
#
# 做什么:把 Observation 规整成下游可消费的 manifest 形态。
# 不做什么:不重试、不改语义、不处理 EXCEPTION(runner 按 on_error 转 typed
# failure Observation,observe 只接 typed Observation,违反 ADR-0211 §1.1 W-8)。
#
# ADR-0211 §1.1 W-1/W-2/W-3:keyword-only / typed / 无 framework ctx。
# ADR-0211 §5.3:一个 Worker 一个动词 —— observe 只做"呈现"。
#
# delete-when:无。

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.models.core.execution.decision import Observation
from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier


# ---------------------------------------------------------------------------
# Carrier
# ---------------------------------------------------------------------------
_CARRIER = LabCarrier(
    id="lab.act.observe",
    stage="act",
    kind="TRANSFORMER",
    description="act.observe — Observation → manifest.",
    node_id="observe",
    source_module="lca.plugins.lab.act.observe.plugin",
    source_class="observe",
    provides=("lab.act.observe.out:observation",),
    requires=("lab.act.execute.out:observation",),
    emits=("lab.act.observe.out:observation",),
    inputs=(("observation", "observation", True),),
    outputs=(("observation", "manifest"),),
    out_capabilities=("lab.act.observe.out:observation",),
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


# ---------------------------------------------------------------------------
# Typed worker —— 纯函数,5 行。
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ObservationManifest:
    """act.observe 产出:model-visible 端可消费的 manifest 形态。"""

    observation_id: str
    success: bool
    payload: Any
    content_type: str
    tool_call_id: str | None
    error: str | None
    latency_ms: int


def observe(*, observation: Observation) -> ObservationManifest:
    """把 Observation 规整成 ObservationManifest。"""
    return ObservationManifest(
        observation_id=observation.observation_id,
        success=observation.success,
        payload=observation.payload,
        content_type=observation.content_type.value,
        tool_call_id=observation.tool_call_id,
        error=observation.error,
        latency_ms=observation.latency_ms,
    )


__all__ = ["ObservationManifest", "observe", "setup"]
