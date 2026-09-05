"""Session-backed WritePort for loop_cursor EP events (ADR-0186 convergence).

cursor 的 6 字段 :class:`~lca.infrastructure.observability.loop_cursor._spine_port.WritePort`
append 经本 adapter 落到当前 run 的
:class:`~lca.plugins.session.runtime.session.Session`(单一生产入口
``Session.append``),不再走 legacy spine 链
(``SpineWritePortAdapter`` → ``EventSpine.append`` → FileSink)。

Layering: infrastructure 不得 import plugins,故 Session 侧 WritePort 实现住在
plugin 层(``lca.plugins.session.runtime``),由 transport builder 在
``bind_run_event_session`` 成功后注入 cursor(见
``handlers/runs/session/builder.py``)。

字段映射与 ``write_port_append`` 一致:``incarnation`` 并入 payload;返回 cursor
传入的 ``seq``(WritePort 语义,SSOT seq 不因端口漂移)。``run_id`` 隐含于 per-run
Session;``phase`` 是 cursor 状态,Session event 无对应槽位,phase-sensitive EP
的 payload 已自带 ``phase`` 键。

无静默回退:未 bind run session 时 fail-loud(构造期抛错);回退到 spine port 的
决策属于装配方(builder),不在本 adapter 内。
"""

from __future__ import annotations

from typing import Any

from lca.plugins.session.runtime.session import Session

__all__ = ["SessionWritePortAdapter"]


class SessionWritePortAdapter:
    """把 loop_cursor 的 WritePort append 路由到当前 run 的 ``Session.append``。

    cursor 唯一允许调用的写入面是 ``WritePort``(6 字段 append)。本 adapter 是
    Session 侧实现:``execution_point`` 作 session event ``type``,``payload``
    并入 ``incarnation`` 作 ``data``,经 ``Session.append`` 落 in-process 日志。
    Session 词表开放(``type`` 仅校验非空字符串),cursor EP 均登记在
    ``SPINE_EXECUTION_POINTS`` 闭集,无新增词表。

    构造接受 run bind 产出的 ``RunEventSessionBridge``(读 ``.inner``)或裸
    runtime :class:`Session`(测试便利);解析不到 Session 时 fail-loud。
    """

    __slots__ = ("_session",)

    def __init__(self, run_session: object) -> None:
        """precondition: ``run_session`` 是已 bind 的 run session bridge 或 Session。

        失败语义: ``None`` / 解析不到 runtime Session 抛 :class:`ValueError`
        (fail-loud,不在 adapter 内回退 spine)。
        """
        session = self._resolve(run_session)
        if session is None:
            raise ValueError(
                "SessionWritePortAdapter requires a bound run session "
                "(bridge exposing `.inner` or a runtime Session); got "
                f"{type(run_session).__name__}"
            )
        self._session = session

    @staticmethod
    def _resolve(target: object) -> Session | None:
        """从 bridge / Session 解析出 runtime Session;解析不到返回 ``None``。"""
        if isinstance(target, Session):
            return target
        inner = getattr(target, "inner", None)
        if isinstance(inner, Session):
            return inner
        return None

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
        """WritePort append → ``Session.append(execution_point, data)``;返回 ``seq``。

        ``data = {**payload, "incarnation": incarnation}``(与 ``write_port_append``
        的 incarnation 并入一致)。``run_id`` / ``phase`` 不单独入 data(理由见模块
        docstring)。``Session.append`` 校验失败(非 JSON 可序列化 data)上抛,日志不变。
        """
        del run_id, phase  # per-run Session 隐含 run_id;phase 无 Session 槽位
        data = {**payload, "incarnation": incarnation}
        self._session.append(execution_point, data)
        return seq
