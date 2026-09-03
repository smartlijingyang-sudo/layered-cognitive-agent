"""LoopCursorFactory — Profile 选择装配入口(ADR-0088 + ADR-0169 D14 / PR-14)。

Profile YAML 通过 ``loop_cursor.spine_default`` bundle 注入本工厂;
调用方提供 run_id + trace_id + spine 句柄即可派生 ``StdLoopCursor``。

incarnation 显式身份(ADR-0169 D6 / L14):
- 首次 :meth:`from_profile` 调用 → incarnation_seq = 1
- fork 路径 → ``cursor.fork(...)`` 内部 ``Incarnation.child()`` 自增
- plan_ref 从 profile 上读(协议面 ``plan_ref: str``,无该字段视为构造错误 —
  不再 silent fallback ``"default"``,因为生产路径 profile duck-type 由
  :class:`lca.plugins.transport.webserver.handlers.runs.session.builder._ProfileProxy`
  注入,且 :meth:`RunSessionBuilder._compute_plan_ref` 已经在 build 阶段
  把真 plan_ref 填到 SSOT ``session.plan_ref``,这里再读 duck-typed
  ``getattr(profile, "plan_ref", "default")`` 反而是历史回退)。
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
        # ADR-0068 §决策二 + ADR-0169 D6:cursor 的 plan_ref 直接来自
        # profile.``plan_ref`` 字段(由 RunSessionBuilder._compute_plan_ref
        # 写入的 SSOT)。这是 cursor.incarnation.plan_ref 的唯一来源。
        # 之前的 ``getattr(profile, "plan_ref", "default")`` 历史兜底
        # 已被删:cursor 的 identity 不应 silent 落到 ``"default"``。
        # profile 必须显式声明 ``plan_ref``,构造时缺字段向上抛清晰错误
        # 而不是 silent 默认。
        if not hasattr(profile, "plan_ref"):
            raise TypeError(
                "LoopCursorFactory.from_profile requires profile.plan_ref; "
                "got "
                f"{type(profile).__name__} (no plan_ref attribute). "
                "Use RunSessionBuilder._compute_plan_ref to derive it before "
                "constructing the cursor."
            )
        plan_ref = profile.plan_ref
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
