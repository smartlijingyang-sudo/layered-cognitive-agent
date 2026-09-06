"""Incarnation —— Session 显式身份(ADR-0169 D6 + ADR-0171 P4)。

``Incarnation`` 是计划维度身份,与 ADR-0095 iteration(尝试维度)正交。
字段语义钉死:
    run_id          — 同一 run 内不变;fork 默认继承(ADR-0171 D2)
    plan_ref        — 计划标识符;plan 变更或 explicit fork → incarnation_seq++
    incarnation_seq — 单调递增,从 1 起

journal envelope 必携带 incarnation(L14 不变量,ADR-0169 L14);
fork 共享 Host 协议见 ADR-0171。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Incarnation:
    """Session 显式身份(ADR-0169 D6 / L14)。"""

    run_id: str
    plan_ref: str
    incarnation_seq: int  # monotonic, starts at 1

    def __post_init__(self) -> None:
        if self.incarnation_seq < 1:
            raise ValueError(f"incarnation_seq must be >= 1, got {self.incarnation_seq!r}")

    def child(self) -> Incarnation:
        """派生 child incarnation:继承 run_id + plan_ref,seq += 1(ADR-0171 P4)。

        用于 fork —— child cursor 默认共享 parent 的 run_id + plan_ref,
        仅递增 incarnation_seq 区分 receipt 序列。
        """
        return Incarnation(
            run_id=self.run_id,
            plan_ref=self.plan_ref,
            incarnation_seq=self.incarnation_seq + 1,
        )


class IncarnationRegistry(Protocol):
    """按 run_id 注册 + 派生 Incarnation(ADR-0169 D6)。

    register   — 首次见到某 run_id 时记录初始 Incarnation(seq=1)
    lookup     — 按 run_id 查当前 Incarnation
    derive_for_plan — 同一 run 切换 plan_ref:seq += 1
    """

    def register(self, run_id: str, plan_ref: str) -> Incarnation: ...

    def lookup(self, run_id: str) -> Incarnation | None: ...

    def derive_for_plan(self, run_id: str, plan_ref: str) -> Incarnation: ...


__all__ = ["Incarnation", "IncarnationRegistry"]
