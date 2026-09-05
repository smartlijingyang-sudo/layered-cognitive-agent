"""Session 事件词表与读路径 fail-closed 校验（DSH known-event-types 对位）。

本构建的「已知 type」= ``@session_event`` 注册表 + spine surface 闭集。
带 ``ignorable=True`` 的未知 type 允许存在于 log 中（读时跳过,不拒开）。
"""

from __future__ import annotations

from lca.contracts.harness import memory as _memory_events  # noqa: F401 — register types
from lca.contracts.harness.tasks.session import event_registry
from lca_kernel.events.fold import SURFACE_EVENT_TYPES

__all__ = [
    "UnknownSessionEventTypeError",
    "known_session_event_types",
    "validate_event_type_for_read",
]


class UnknownSessionEventTypeError(ValueError):
    """未知且非 ignorable 的 session event type —— 读路径 fail-closed。"""

    def __init__(self, event_type: str) -> None:
        super().__init__(
            f"unknown session event type={event_type!r} and not ignorable; "
            "refusing to open log"
        )
        self.event_type = event_type


def known_session_event_types() -> frozenset[str]:
    """本构建理解的 session event type 闭集（yaml/decorator 注册 + surface 词表）。"""
    types = set(event_registry().keys())
    types.update(SURFACE_EVENT_TYPES)
    return frozenset(types)


def validate_event_type_for_read(event_type: str, *, ignorable: bool = False) -> None:
    """读路径 type 校验:未知且非 ignorable → 抛错;ignorable → 放行。"""
    if ignorable:
        return
    if event_type not in known_session_event_types():
        raise UnknownSessionEventTypeError(event_type)
