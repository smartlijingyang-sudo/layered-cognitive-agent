"""LoopCursor ↔ Spine / ContextVar 桥(ADR-0169 PR-1 §S1 业务迁 cursor 第一步)。

本模块**仅**提供两个薄壳,不在此引入新控制面:

- :class:`SpineWritePortAdapter` —— 把 :class:`EventSpine` 包成
  :class:`WritePort` 协议位,让 :class:`StdLoopCursor` 可走同一 spine 句柄
  (事件不二次落盘;cursor 是事件源端而非 sink)。
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

# EventSpine.append 的真实签名跟 WritePort 协议位不同;这里给出
# 字段名映射,只把 cursor 关心的 4 个字段映射过去。
#
#   EventSpine.append(
#       execution_point, caller_payload, channel, outcome, span_ctx,
#       phase, reason, when,
#   )
#   ↳ WritePort.append(
#       execution_point, payload, run_id, seq, incarnation, phase,
#   )
#
# seq / run_id / incarnation 由 EventSpine 内部 SpineContext 主导分配;
# cursor 给的 seq / incarnation / run_id 仅当 EventSpine 接受,本 adapter
# 用 ``SpineContext.set_run`` 同步,然后 :meth:`EventSpine.append` 内部
# 依然以 SpineContext 为准(SSOT 不漂)。


def _set_run_on_spine(event_spine: Any, run_id: str, seq: int) -> None:
    """让 :class:`EventSpine` 接下来 ``append`` 时把这条事件关联到当前 run。

    :class:`EventSpine` 通过 :func:`SpineContext.get_run` 取 run_id
    (见 ``event_spine.append`` 的内部实现);这里复用同一 :class:`SpineContext`
    钩子,而**不**给 :class:`EventSpine` 加新方法。
    """
    from lca.infrastructure.observability.spine.context import SpineContext

    SpineContext.set_run(run_id)


class SpineWritePortAdapter:
    """EventSpine → :class:`WritePort` 协议位薄壳。

    cursor 唯一允许调用的 spine 面是 :class:`WritePort` (ADR-0169 D1 / L10);
    EventSpine 字段更多但语义同构(都是单写 append-only)。
    本 adapter **不** 二次写盘,只是把 cursor 的 WritePort API 翻译到
    EventSpine 真实 API。

    与 ADR-0169 L10 的关系:L10 是「events.jsonl 由 EventSpine.append 唯一写入」
    —— cursor 通过本 adapter 调到的也是 EventSpine.append,故 L10 不漂。
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
        """L10 单写: 直接落 EventSpine.append,字段映射一次。

        Note
        ----
        :class:`EventSpine.append` 内部 seq / run_id 走 :class:`SpineContext`
        自增;cursor 给的 seq 仅当 :class:`EventSpine` 接受 (as payload),
        真实 seq 由 SpineContext 决定。payload 携带 incarnation 字段供
        ADR-0169 L14 envelope 校验。
        """
        _set_run_on_spine(self._spine, run_id, seq)
        # incarnation 进 payload(L14 envelope);seq / run_id 由 SpineContext 管。
        merged_payload = {**payload, "incarnation": incarnation}
        self._spine.append(
            execution_point=execution_point,
            caller_payload=merged_payload,
            channel="fact",
            outcome=None,
            span_ctx=None,
            phase="live" if phase is None else str(phase),
            reason=None,
            when=None,
        )
        return seq


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
