"""统一事件描述符查询层（ADR-0063 PR-7 source inversion）。

``descriptor_for()`` 与 ``may_export_externally()`` 现在只读 ``EVENT_DESCRIPTOR_REGISTRY``。
投影器、Inspector、SSE 帧选择器统一调入口；不再有第二张 catalog 表。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.models.observability.event import EventAudience, EventDescriptor, EventSensitivity
from lca.contracts.models.observability.journal import JournalEvent
from lca.layer0_infra.observability.event_descriptor_registry import (
    UnknownEventDescriptorError,
)
from lca.layer0_infra.observability.event_descriptors_data import build_default_registry

if TYPE_CHECKING:
    pass


# 启动期 bootstrap：49 个内置事件描述符入册。cordis 启动后插件可继续 register。
EVENT_DESCRIPTOR_REGISTRY = build_default_registry()


def descriptor_for(event: JournalEvent | str) -> EventDescriptor:
    """返回已登记事件的唯一治理描述符。"""
    type_name = event if isinstance(event, str) else type(event).__name__
    try:
        return EVENT_DESCRIPTOR_REGISTRY.require(type_name)
    except UnknownEventDescriptorError as exc:
        raise KeyError(f"未登记的运行事件描述符：{type_name}") from exc


def may_export_externally(event: JournalEvent | str) -> bool:
    """外部 OTel/Langfuse 投影只接收非受限、非机密事件。"""
    descriptor = descriptor_for(event)
    return (
        descriptor.audience is not EventAudience.RESTRICTED
        and descriptor.sensitivity is not EventSensitivity.CONFIDENTIAL
    )


__all__ = ["EVENT_DESCRIPTOR_REGISTRY", "descriptor_for", "may_export_externally"]