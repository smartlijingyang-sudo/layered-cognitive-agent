"""spine_reflector_perception plugin（ADR-0181 PR-6 / ADR-0183 PR-7）。

PR-6：perception 维度 6 EP（新加，old manifest 没有）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.payloads import Category, SpineEventPayload

if TYPE_CHECKING:
    from lca_kernel.events.bus import EventRef

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

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
    "setup",
]




class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="events.spine.reflector.perception",
    provides=["event.bus.reflector.perception"],
    requires=["event.bus"],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "perception publisher（ADR-0181）：event.bus.reflector.perception 由本 plugin 发出。"
    ),
    test_suite="tests/plugins/events/publishers/test_events_spine_reflector_perception.py",
    functional_group=FunctionalGroup.G4_PERCEPTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G4_PERCEPTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(
            descriptors=("event.bus.reflector.perception.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(
            "spine.perception.observe",
            "spine.perception.attention.focus",
            "spine.perception.attention.blur",
            "spine.perception.signal.detected",
            "spine.perception.fused",
            "spine.perception.artifact.built",
        ),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """events.spine.reflector.perception boot：注册 publisher marker 给 ctx。"""
    ctx.provide("event.bus.reflector.perception", ReflectorClass)

