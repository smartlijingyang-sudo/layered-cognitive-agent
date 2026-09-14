"""StdLoopCursor — 默认实现(ADR-0169 D1 / D8)。

仅持 spine handle + _state;不持 deriver / projections / persistence /
llm hook / model_visible recorder 实例(评审 S1 处方,AST scan 验证)。
构造器签名只接 spine + identity(metadata);不接 host / persistence / capture。

公共面(单生产者):
- :meth:`advance` —— phase.<name>.fold 唯一生产者
step 边界由 ModelVisibleHook 唯一驱动(``spine.llm.request.header``),本
cursor 不持 step_index 计数器。
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
    - 状态机非法转移抛 CursorError

    单生产者 SSOT:
    - :meth:`advance` —— phase.<name>.fold 唯一生产者
    - step 边界由 hook 端 ``spine.llm.request.header`` 唯一发射
      (本 cursor 不持 step_index)

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

    # ── step 计数器(SSOT=hook 端,本 cursor 不参与)──────────────
    # 历史:曾持有 step_index 自增 + writable.step.start EP 派生。
    # 砍掉:step 边界由 ModelVisibleHook 唯一驱动(spine.llm.request.header
    # payload.step_id),cursor 只持 phase。

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
        if phase not in _VALID_PHASES:
            raise CursorError(f"invalid phase {phase!r}; gate is Think sub-chain (ADR-0194 §1.3)")
        s = self._state
        # stop → perceive 触发新 iteration
        if s.phase == "stop" and phase == "perceive":
            s.iteration += 1
            s.attempt_in_step = 0
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
            },
        )
        return self.snapshot


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
