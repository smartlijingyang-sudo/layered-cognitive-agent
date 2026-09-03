"""spine_reflector_kernel_loop plugin（ADR-0181 PR-4 / ADR-0183 PR-7）。

PR-4：kernel.boot / loop.fork 全部 3 emit 下沉到 EventBus.publish：
- kernel.boot.start / .completed
- loop.fork
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca_kernel.events.payloads import Category, SpineEventPayload
from lca_kernel.events.payloads_spine import _SPINE_EP_TO_CATEGORY

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
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
) -> EventRef:
    """内部 helper：构造 SpineEventPayload + EventBus.publish。

    EventBus 走函数内 lazy import，避免 plugin import 时触发
    lca.infrastructure.observability ↔ lca_kernel 链路 circular import。
    """
    from lca_kernel.events.bus import EventBus

    cat_str = _SPINE_EP_TO_CATEGORY[execution_point]
    sp = SpineEventPayload(
        category=Category(cat_str),
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    return EventBus.default().publish(sp, producer=ReflectorClass)


# ── kernel.boot.start / .completed ────────────────────────────────────


def emit_kernel_boot_start(*, profile: str) -> EventRef:
    """Emit at kernel boot start; ``profile`` is the resolved profile name."""
    return _send(
        execution_point="kernel.boot.start",
        channel="control",
        payload={"profile": profile},
    )


def emit_kernel_boot_completed(*, profile: str, outcome: str = "success") -> EventRef:
    """Emit at kernel boot completion; default outcome ``success``."""
    return _send(
        execution_point="kernel.boot.completed",
        channel="control",
        payload={"profile": profile, "outcome": outcome},
    )


# ── loop.fork ─────────────────────────────────────────────────────────


def emit_loop_fork(*, child_role: str, parent_step: int) -> EventRef:
    """Emit when a loop cursor forks into a child agent; ADR-0169."""
    return _send(
        execution_point="loop.fork",
        channel="control",
        payload={"child_role": child_role, "parent_step": parent_step},
    )


__all__ = [
    "ReflectorClass",
    "emit_kernel_boot_completed",
    "emit_kernel_boot_start",
    "emit_loop_fork",
    "setup",
]




class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="events.spine.reflector.kernel_loop",
    provides=["event.bus.reflector.kernel_loop"],
    requires=["event.bus"],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "kernel_loop publisher（ADR-0181）：event.bus.reflector.kernel_loop 由本 plugin 发出。"
    ),
    test_suite="tests/plugins/events/publishers/test_events_spine_reflector_kernel_loop.py",
    functional_group=FunctionalGroup.G0_CON_KERNEL,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G0_CON_KERNEL,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(
            descriptors=("event.bus.reflector.kernel_loop.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(
            "spine.kernel.boot.start",
            "spine.kernel.boot.completed",
            "spine.loop.fork",
        ),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """events.spine.reflector.kernel_loop boot：注册 publisher marker 给 ctx。"""
    ctx.provide("event.bus.reflector.kernel_loop", ReflectorClass)

