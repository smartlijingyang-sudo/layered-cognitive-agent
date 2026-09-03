"""spine_reflector_boot plugin（ADR-0181 PR-6 / ADR-0183 PR-7）。

PR-6：boot 维度 3 EP（新加，old manifest 没有）。
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


def emit_boot_profile_resolved(*, profile: str, plugins: int) -> EventRef:
    return _send(
        category="spine.boot.profile.resolved",
        execution_point="boot.profile.resolved",
        channel="control",
        payload={"profile": profile, "plugins": plugins},
    )


def emit_boot_plugin_fiber_spawned(*, plugin_id: str, layer: str) -> EventRef:
    return _send(
        category="spine.boot.plugin.fiber.spawned",
        execution_point="boot.plugin.fiber.spawned",
        channel="control",
        payload={"plugin_id": plugin_id, "layer": layer},
    )


def emit_boot_observability_assembled(*, sinks: int, derivers: int) -> EventRef:
    return _send(
        category="spine.boot.observability.assembled",
        execution_point="boot.observability.assembled",
        channel="control",
        payload={"sinks": sinks, "derivers": derivers},
    )


__all__ = [
    "ReflectorClass",
    "emit_boot_observability_assembled",
    "emit_boot_plugin_fiber_spawned",
    "emit_boot_profile_resolved",
]
