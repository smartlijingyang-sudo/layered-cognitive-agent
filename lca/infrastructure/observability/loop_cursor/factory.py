"""LoopCursorFactory — Profile 选择装配入口(ADR-0088 + ADR-0169 D14 / PR-14)。

Profile YAML 通过 ``loop_cursor.spine_default`` bundle 注入本工厂;
调用方提供 run_id + trace_id + spine 句柄即可派生 ``StdLoopCursor``。

incarnation 显式身份(ADR-0169 D6 / L14):
- 首次 :meth:`from_profile` 调用 → incarnation_seq = 1
- fork 路径 → ``cursor.fork(...)`` 内部 ``Incarnation.child()`` 自增
- plan_ref 从 profile 上读;无则 fallback ``"default"``

返回值:
- :meth:`from_profile` 返回 ``(StdLoopCursor, Incarnation)`` 二元组;
  调用方可同时拿到 cursor 和其 incarnation 身份(供 fork / Capture 读取)。
"""

from __future__ import annotations

from lca.contracts.observability.incarnation import Incarnation
from lca.infrastructure.observability.loop_cursor._spine_port import WritePort
from lca.infrastructure.observability.loop_cursor.std import StdLoopCursor


class LoopCursorFactory:
    """工厂入口 — Profile 装配出 ``StdLoopCursor``(默认实现 = StdLoopCursor)。

    本 PR 阶段只支持 ``StdLoopCursor`` 默认装配;后续 PR-6/14 之后才会扩展
    "profile.observability.loop_cursor.implementation = in_memory" 等
    profile 替换能力。
    """

    @staticmethod
    def from_profile(
        *,
        profile: object,
        run_id: str,
        trace_id: str,
        spine: WritePort,
    ) -> tuple[StdLoopCursor, Incarnation]:
        """构造 ``(StdLoopCursor, Incarnation)`` 二元组(ADR-0169 D6 / PR-25)。

        Parameters
        ----------
        profile:
            Profile / ResolvedProfile / 任意 duck-typed 对象;仅读
            ``plan_ref`` 字段(可有可无,缺省 ``"default"``)。
        run_id:
            Run 唯一标识(由调用方注入;从 cordis Context 派生)。
        trace_id:
            Trace 唯一标识(同 run 可有多 trace;并发 run 之间隔离)。
        spine:
            :class:`WritePort` 协议位 — :class:`StdLoopCursor` 唯一允许调用的
            spine 面(ADR-0169 D1 / L10)。

        Returns
        -------
        tuple[StdLoopCursor, Incarnation]
            cursor + incarnation 二元组;incarnation 供 fork / Capture 读取。
        """
        plan_ref = getattr(profile, "plan_ref", "default")
        incarnation = Incarnation(
            run_id=run_id,
            plan_ref=str(plan_ref),
            incarnation_seq=1,
        )
        cursor = StdLoopCursor(
            spine=spine,
            run_id=run_id,
            trace_id=trace_id,
            incarnation=incarnation,
        )
        return cursor, incarnation


__all__ = ["LoopCursorFactory"]
