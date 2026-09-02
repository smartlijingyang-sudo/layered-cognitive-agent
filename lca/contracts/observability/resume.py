"""halt-resume 协议契约(ADR-0173 D2)。

``ResumeSpec`` 是 spatial-temporal runtime 重建 ``LoopCursor`` 时携带的
最小身份与意图(snapshot + iteration_reason)。本 dataclass 冻结,任何字段
变更必须先有 ADR 改 ADR-0173。

设计要点(ADR-0173 P1 / D2 / D3):
- 字段平面最小:``run_id`` + ``plan_ref`` + ``incarnation_seq`` 是 cursor 身份,
  ``iteration`` / ``step_index`` / ``phase`` 是 halted 时 cursor.snapshot 的
  派生投影。
- ``iteration_reason`` 必为 close-set 之一,默认 ``"checkpoint_resume"``;
  旧 cursor 实例**不复用**(I-RESUME-1),新 cursor 由 host / persistence 状态
  派生出来。
- ``halt != close``(评审 §S10 + §潜在 #8):``close`` 释放资源,
  ``halt`` 保留 cursor 实例,等 spatial-temporal runtime 走 resume 重建。

``IterationReason`` is the union declared in
``contracts.observability.loop_cursor`` — single source of truth
(ADR-0169 §D3 L1 close-set; introduced in two modules historically,
consolidated here so callers can rely on a stable Literal). ``resume``
re-exports the alias under its historic name for backwards
compatibility with downstream imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.observability.loop_cursor import IterationReason, PhaseName

__all__ = ["IterationReason", "ResumeSpec"]


@dataclass(frozen=True)
class ResumeSpec:
    """halt-resume 协议入口契约(ADR-0173 D2)。

    由 spatial-temporal runtime 持有,用于派生新 ``LoopCursor`` 实例;
    新 cursor 的 ``snapshot.phase`` / ``iteration`` / ``step_index`` 由本 spec
    直接注入,``incarnation`` 由 ``Incarnation`` 派生。
    """

    run_id: str
    plan_ref: str
    incarnation_seq: int
    iteration: int
    step_index: int
    phase: PhaseName
    iteration_reason: IterationReason = "checkpoint_resume"
