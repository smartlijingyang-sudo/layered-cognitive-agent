"""SpineWritePortAdapter —— Spine 句柄到 WritePort 协议的薄 façade。

ADR-0169 D1 / L10:cursor 唯一允许调用的 spine 面是 :class:`WritePort`;
字段映射与写入实现收口在 :func:`write_port_append`(ADR-0183 PR-9 单一
spine 写入入口),本类只保签名兼容,不重复实现 append。

历史:本类曾在 ``lca.infrastructure.observability.loop_cursor.bind.bind``
(specced for PR-1.5) 与 :class:`CoordinatorAdapter` 同位;Task 5 删除了
``bind/bind.py`` 整个模块(其暴露的 ``install_run_cursor`` /
``reset_run_cursor`` 是 ``_current_cursor`` ContextVar 的 thin re-export)。
本类与 ContextVar 无依赖,迁到独立模块以保持其唯一职责(协议适配)。
"""

from __future__ import annotations

from typing import Any

from lca.infrastructure.observability.loop_cursor.spine._spine_port import (
    write_port_append,
)


class SpineWritePortAdapter:
    """spine 句柄 → :class:`WritePort` 协议位的 façade。

    cursor 唯一允许调用的 spine 面是 :class:`WritePort`(ADR-0169 D1 / L10);
    ADR-0183 PR-9 之后字段映射与写入实现收口在
    :func:`write_port_append` → ``spine_port_append``(单一写入实现),
    本 adapter 不重复实现 ``append``,只保签名兼容(外部调用方与
    :class:`WritePort` 契约不破)。
    """

    __slots__ = ("_spine",)

    def __init__(self, event_spine: Any) -> None:
        # duck-type:不必强制 isinstance(EventSpine);
        # 任何有 append(...) + SpineContext 钩子的对象都接受
        self._spine = event_spine

    def append(
        self,
        *,
        execution_point: str,
        payload: dict[str, Any],
        run_id: str,
        seq: int,
        incarnation: int,
        phase: str | None,
    ) -> int:
        """Façade — 转发 ``write_port_append`` 单一写入入口。"""
        return write_port_append(
            self._spine,
            execution_point=execution_point,
            payload=payload,
            run_id=run_id,
            seq=seq,
            incarnation=incarnation,
            phase=phase,
        )


__all__ = ["SpineWritePortAdapter"]
