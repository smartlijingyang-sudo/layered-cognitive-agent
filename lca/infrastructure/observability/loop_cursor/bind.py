"""LoopCursor ↔ Spine / ContextVar 桥(ADR-0169 PR-1 §S1 业务迁 cursor 第一步)。

本模块**仅**提供两个薄壳,不在此引入新控制面:

- :class:`SpineWritePortAdapter` —— 把 spine 句柄包成 :class:`WritePort`
  协议位的 façade;字段映射与写入实现收口在
  ``_spine_port.write_port_append`` / ``spine_port_append``(ADR-0183 PR-9
  单一 spine 写入入口),本类只保签名兼容,不重复实现 append。
- :func:`install_run_cursor` —— 把 cursor 绑到 ContextVar 并返回 reset token,
  wiring 层拿到 token 在 run 结束 (close) 时释放。

删除条件
========
PR-3 / S3 装配切换到 :class:`LoopCursorFactory.from_profile` 后,本模块仍保留
(``Profile.selected_runtime_factory`` 调用前,builder 仍是装配主入口);
PR-21~24 业务真正全面接管 cursor 后,本模块降级为「back-compat glue」,不再
新增调用方。
"""

# COMPAT(delete-when: PR-21~24 业务全部走 cursor 参数直传,不再依赖 ContextVar 隐式注入, tracking: ADR-0169-task-1.5)
# 接入期:web-standard run 通过 ContextVar 注入 cursor;业务路径
# (perceive_hub / reasoner / tool_body) 取 cursor 走本模块暴露的
# ``install_run_cursor`` + ``get_current_cursor`` (re-export 自 coordinator_adapter)。
# 删除条件:``grep _current_cursor / get_current_cursor`` in ``lca/`` 输出 0。

from __future__ import annotations

from contextvars import Token
from typing import Any

from lca.contracts.observability.loop_cursor import LoopCursor
from lca.infrastructure.observability.loop_cursor._spine_port import write_port_append


class SpineWritePortAdapter:
    """spine 句柄 → :class:`WritePort` 协议位的 façade。

    cursor 唯一允许调用的 spine 面是 :class:`WritePort`(ADR-0169 D1 / L10);
    ADR-0183 PR-9 之后字段映射与写入实现收口在
    :func:`lca.infrastructure.observability.loop_cursor._spine_port.write_port_append`
    → ``spine_port_append``(单一写入实现),本 adapter 不重复实现
    ``append``,只保签名兼容(外部调用方与 :class:`WritePort` 契约不破)。
    与 L10 的关系不变:events 仍由单一写入实现经 FileSink 落
    ``<run_id>.spine.jsonl``,cursor 是事件源端而非 sink。
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
        """Façade — 转发 ``_spine_port.write_port_append`` 单一写入入口。"""
        return write_port_append(
            self._spine,
            execution_point=execution_point,
            payload=payload,
            run_id=run_id,
            seq=seq,
            incarnation=incarnation,
            phase=phase,
        )


def install_run_cursor(cursor: LoopCursor) -> Token[Any]:
    """把 cursor 绑到 ContextVar;返回 reset token(由 caller 在 close 时释放)。

    见 :mod:`lca.infrastructure.observability.loop_cursor.coordinator_adapter`
    的 ``bind_current_cursor`` —— 本函数是其 thin re-export,放在 loop_cursor
    默认导出里让 transport 层只 import 一个符号。

    Examples
    --------
    >>> token = install_run_cursor(cursor)
    >>> try:
    ...     ...
    ... finally:
    ...     reset_run_cursor(token)
    """
    from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
        bind_current_cursor,
    )

    return bind_current_cursor(cursor)


def reset_run_cursor(token: Token[Any]) -> None:
    """释放 ``install_run_cursor`` 返回的 token。"""
    from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
        reset_current_cursor,
    )

    reset_current_cursor(token)


__all__ = [
    "SpineWritePortAdapter",
    "install_run_cursor",
    "reset_run_cursor",
]
