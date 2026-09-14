"""StdLoopCursor — 默认实现(ADR-0169 D1 / D8)。

仅持 spine handle + _state;不持 deriver / projections / persistence /
llm hook / model_visible recorder 实例(评审 S1 处方,AST scan 验证)。
构造器签名只接 spine + identity(metadata);不接 host / persistence / capture。

公共面收口(2026-09-14 dead-code 修剪):
- 生产路径只剩 :meth:`advance` (LLM adapter ``phase.think.fold`` SSOT)
  与 :meth:`open_step` (hook ``ModelVisibleHook.capture_pre_llm``)。
- ``record_thinking`` / ``record_tool_call`` / ``record_tool_result`` /
  ``record_request_header`` / ``halt`` / ``close`` / ``fork`` /
  ``resume_cursor`` 全部无生产 caller,已删除。
- ``_emit_step_end`` 随 ``close`` / ``halt`` 死代码一同删除;停 phase 由
  :meth:`advance` 内联收口(``advance("stop")`` 直接改 state、不发 EP)。
- :class:`Runtime` 收尾走 :class:`CloseBarrier`(:mod:`close.barrier_impl`),
  不再调 cursor.close,故 cursor.close 无 caller。
"""

from __future__ import annotations

from typing import Literal, get_args

from lca.contracts.observability.core.incarnation import Incarnation
from lca.contracts.observability.cursor.loop_cursor import (
    CursorError,
    CursorSnapshot,
    LoopCursor,
    PhaseName,
)
from lca.contracts.observability.cursor.loop_cursor_payloads import PhaseFoldPayload
from lca.infrastructure.observability.loop_cursor.spine._spine_port import WritePort
from lca.infrastructure.observability.loop_cursor.state.state import _CursorState

_VALID_PHASES = frozenset(get_args(PhaseName))


class StdLoopCursor:
    """默认 LoopCursor 实现 — 薄控制状态机(ADR-0169 P1 / D1)。

    状态转移合法性:
    - 进入 phase.X 后,record_X 必须在 X phase 窗口内调用
    - close() 之后所有 advance / open_step 抛 CursorError

    显式 step 边界(ADR-0184 D6):
    - :meth:`open_step` 发 ``writable.step.start``(唯一生产路径)
    - ``phase.<name>.fold`` 由 :meth:`advance` 派生;``phase="stop"`` 时
      关 state 但不显式发 ``writable.step.end``(只有 LLM 边界会开窗)。

    incarnation 显式身份(ADR-0169 D6 / L14):
    - cursor 持有 frozen Incarnation(run_id + plan_ref + incarnation_seq)
    - snapshot.incarnation 派生自 Incarnation.incarnation_seq
    - spine payload 携带 incarnation(plan_ref + seq),envelope 必携带(L14)
    """

    def __init__(
        self,
        *,
        spine: WritePort,
        run_id: str,
        trace_id: str,
        incarnation: Incarnation,
    ) -> None:
        self._spine = spine
        self._state = _CursorState(
            run_id=run_id,
            trace_id=trace_id,
            incarnation=incarnation,
        )

    @property
    def snapshot(self) -> CursorSnapshot:
        s = self._state
        return CursorSnapshot(
            run_id=s.run_id,
            trace_id=s.trace_id,
            incarnation=s.incarnation.incarnation_seq,
            step_id=s.step_id,
            step_index=s.step_index,
            iteration=s.iteration,
            attempt_in_step=s.attempt_in_step,
            phase=s.phase,
            iteration_reason=s.iteration_reason,
            stop_signal=s.stop_signal,
            seq=s.seq,
        )

    @property
    def incarnation(self) -> Incarnation:
        """暴露当前 cursor 的显式身份(ADR-0169 D6);供 Capture 读取。"""
        return self._state.incarnation

    @property
    def plan_ref(self) -> str:
        """Plan identity 顶层 accessor — ``cursor.plan_ref`` 等价于 ``cursor.incarnation.plan_ref``。

        ADR-0068 §决策二 + ADR-0169 D6:plan_ref 是 cursor 的显式身份之一
        (与 run_id / incarnation_seq 同级),reader 不必穿透 incarnation 字段
        就能拿到 16-hex plan ID。让 interpreter / capture 都能直读,
        避免 ``getattr(cursor, "plan_ref", None)`` 这种 duck-type 谎言。

        与 :attr:`Incarnation.plan_ref` 同源(永远相等),只是 alias。
        """
        return self._state.incarnation.plan_ref

    # ── spine append helper ─────────────────────────────────────
    def _append(self, execution_point: str, payload: dict) -> int:
        s = self._state
        s.seq += 1
        return self._spine.append(
            execution_point=execution_point,
            payload=payload,
            run_id=s.run_id,
            seq=s.seq,
            incarnation=s.incarnation.incarnation_seq,
            phase=s.phase,
        )

    def _ensure_open(self) -> None:
        if self._state.closed:
            raise CursorError("cursor closed")

    # ── 显式 step 边界(ADR-0184 D6)────────────────────────────────
    def _emit_step_start(self, *, step_id: str) -> None:
        """发射显式 step 边界 ``writable.step.start``,并置 ``step_open``。

        precondition:调用点已完成 step_index / step_id 推进(:meth:`open_step`)。
        写入路径:与 :class:`WritePort` 链
        (``_append`` → ``write_port_append`` → Session.append → spine sink),
        同源同步、无总线旁路。

        payload 契约:``step``(当前 step_index)/ ``run_id`` / ``step_id`` —
        ``step`` / ``run_id`` 与 spine.yaml ``spine.writable.step.start``
        fields 对齐,``step_id`` 为 cursor 侧补充键。**不写 phase 字段**:
        writable.step.start 是 LLM 边界专属 marker,frame.phase 由
        phase.fold 事件统一决定。

        所有权:本方法是 ``writable.step.start`` 的唯一发射点。

        不变量:同 step_id 在已开窗且未关闭时重复调用,frame 折叠(fold
        端 ``_begin_step`` 检测空 frame 同 step_id 原地升级);不写第二
        条 EP —— 避免历史上 duplicate step_id 触发 doctor H3 fail
        (回归 run_c2d944661a78 / run_03cabc8d9559)。
        """
        s = self._state
        if s.step_open and s.step_id == step_id:
            # 重复同 step_id 开窗 = fold 端原地升级,不再发第二条 EP。
            return
        s.step_open = True
        s.step_id = step_id
        self._append(
            execution_point="writable.step.start",
            payload={
                "step": s.step_index,
                "run_id": s.run_id,
                "step_id": step_id,
            },
        )

    # ── 转移(1) ──────────────────────────────────────────────────
    def advance(
        self,
        phase: PhaseName,
        *,
        objective_kind: Literal[
            "user_text", "agent_role", "system_role", "model_name"
        ] = "system_role",
        objective: str = "",
        summary: str = "",
    ) -> CursorSnapshot:
        """Phase 窗口转移,并唯一派生 ``phase.<name>.fold`` EP。

        强类型 payload(ADR-0169 P2 + SSOT 收口):
        - ``objective_kind`` 与 ``objective`` 必须配对 —— 不再接受裸 str,
          杜绝历史 bug(spine 同时出现 objective=模型名 与 objective=用户文本
          两条同 EP,因为 LLM adapter 把 ``objective=model`` 误传给 emit_phase)。
        - 不传 objective 时 objective_kind 默认为 ``system_role``,允许
          perceive / remember / stop 等不带 objective 的相位折叠。
        """
        self._ensure_open()
        if phase not in _VALID_PHASES:
            raise CursorError(
                f"invalid phase {phase!r}; gate is Think sub-chain (ADR-0194 §1.3)"
            )
        s = self._state
        # stop → perceive 触发新 iteration
        if s.phase == "stop" and phase == "perceive":
            s.iteration += 1
            s.attempt_in_step = 0
            s.step_index = 0
        elif s.phase == "stop" and phase != "perceive":
            raise CursorError(f"cannot advance from stop to {phase!r}")
        s.phase = phase
        # 派生 phase.<name>.fold EP(ADR-0169 P2 / L3)—— cursor 是唯一写入者
        fold_payload = PhaseFoldPayload(
            phase=phase,
            objective_kind=objective_kind,
            objective=objective,
            summary=summary,
        )
        self._append(
            execution_point=f"phase.{phase}.fold",
            payload={
                "phase": fold_payload.phase,
                "objective_kind": fold_payload.objective_kind,
                "objective": fold_payload.objective,
                "summary": fold_payload.summary,
                "incarnation": s.incarnation.incarnation_seq,
                "plan_ref": s.incarnation.plan_ref,
                "step_index": s.step_index,
            },
        )
        return self.snapshot

    def open_step(self, step_id: str) -> None:
        """LLM 边界 step 推进 —— L6 自增 + 显式 ``writable.step.start`` 发射。

        hook 路径(ADR-0185 ``ModelVisibleHook.capture_pre_llm``)自行经
        Session 发 ``spine.llm.request.header`` payload;cursor 推进
        ``step_index += 1`` / ``step_id`` / ``attempt_in_step`` 归零,并发
        ``writable.step.start`` 显式边界(ADR-0184 D6)。
        若此处再派生 ``llm.request.header`` EP,fold 会看到双重 step 边,
        故 ``llm.request.header`` 仍由 hook 侧唯一发射,本方法不碰。

        不强制 think 窗口:team 委派时子 Agent 的 LLM 边界可能发生在共享
        cursor 的非 think 相位。已关闭 cursor 调本方法抛 CursorError。

        幂等:同 step_id 在 ``step_open`` 仍为 True 时调用不发第二条 EP
        (见 :meth:`_emit_step_start`)。
        """
        self._ensure_open()
        s = self._state
        # 幂等分支:已开窗且 step_id 相同 → _emit_step_start 内部不再写 EP
        if s.step_open and s.step_id == step_id:
            return
        s.step_index += 1
        s.step_id = step_id
        s.attempt_in_step = 0
        self._emit_step_start(step_id=step_id)


def _static_protocol_check() -> None:
    """编译期检查 StdLoopCursor 满足 LoopCursor Protocol。"""

    class _StubSpine:
        def append(self, **kw: object) -> int:
            return 0

    inc = Incarnation(run_id="r", plan_ref="p", incarnation_seq=1)
    _: LoopCursor = StdLoopCursor(
        spine=_StubSpine(),
        run_id="r",
        trace_id="t",
        incarnation=inc,
    )


__all__ = ["StdLoopCursor"]
