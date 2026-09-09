"""TaskProgress — Decision 的 task-progress observation 四元组 (ADR-0214 §3.1).

本模块是 contracts 层的纯数据契约(AGENTS.md §2.1):
- ``@dataclass(frozen=True, slots=True)``:等价于 Pydantic
  ``extra="forbid"`` + frozen 的 dataclass 形态;LCA contracts 默认用
  dataclass,不引入 Pydantic(已声明)。
- ``__post_init__`` 校验 confidence 闭区间,违反抛 :class:`ContractViolation`。
- ``is_terminal()`` 给 Gate / Projection 用的"任务可停止"判定。

所有权:cognition 在 reasoner 解析阶段必须**显式**构造并填入
:attr:`Decision.task_progress`;默认值仅用于兼容旧测试 / 迁移态代码。
cognition emit 方构造 Decision 时漏传 ``task_progress`` 由
``tests/integration/test_decision_emit_consume.py`` 守卫。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.errors import ContractViolation


@dataclass(frozen=True, slots=True)
class TaskProgress:
    """think step 的任务进度观察面四元组。

    四个字段共同定义 *主动收敛*(ADR-0214 §0.3):

    - :attr:`completed` 单调递增 — Reducer fold 不变式
    - :attr:`remaining` 终态可空 — 中途可减可加,但 fold 后必须满足 schema
    - :attr:`confidence` ∈ [0, 1] — 模型对自身剩余进度的把握度
    - :attr:`termination_reason` 非空 → 强制 STOP(跳过 execute)

    显式构造时:模型必填四元组;默认值 ``()`` / ``0.0`` / ``None`` 仅供
    旧测试 / 迁移期兼容。cognition emit 方必须显式传(详见 ADR-0214 §3.2)。
    """

    completed: tuple[str, ...] = ()
    remaining: tuple[str, ...] = ()
    confidence: float = 0.0
    termination_reason: str | None = None

    def __post_init__(self) -> None:
        # frozen dataclass 不允许运行时 mutate,__post_init__ 是唯一的
        # "构造时校验"入口(等价于 Pydantic frozen + extra="forbid" 的
        # model_validator)。越界 confidence 直接拒绝,绝不静默 clamp
        # (C4/C13 fail-loud)。
        if not isinstance(self.confidence, (int, float)) or isinstance(self.confidence, bool):
            raise ContractViolation(
                f"confidence must be a real number in [0, 1], got {type(self.confidence).__name__}"
            )
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ContractViolation(f"confidence must be in [0, 1], got {self.confidence}")
        if self.completed is not None and not isinstance(self.completed, tuple):
            # 显式接受 list 输入的话,__post_init__ 不在 self.__setattr__
            # 安全点;为 fail-loud 我们直接拒绝非 tuple 输入。
            raise ContractViolation(
                f"completed must be a tuple[str, ...], got {type(self.completed).__name__}"
            )
        if self.remaining is not None and not isinstance(self.remaining, tuple):
            raise ContractViolation(
                f"remaining must be a tuple[str, ...], got {type(self.remaining).__name__}"
            )

    def is_terminal(self) -> bool:
        """是否已收敛(可 RESPOND / 终止)。

        判定:remaining 已耗尽 + confidence 足够高(≥ 0.8)。该阈值与
        MultiToolLoopBreakerGate / TaskProgressGate 共用(PR-B 落地后)。
        """
        return len(self.remaining) == 0 and self.confidence >= 0.8

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TaskProgress):
            return NotImplemented
        return (
            self.completed == other.completed
            and self.remaining == other.remaining
            and self.confidence == other.confidence
            and self.termination_reason == other.termination_reason
        )

    def __hash__(self) -> int:
        return hash((self.completed, self.remaining, self.confidence, self.termination_reason))

    # dataclass(frozen=True) 自带的 __repr__ 已足够;这里补充一个
    # 用作 diagnostics 的人类可读视图。
    def as_dict(self) -> dict[str, Any]:
        return {
            "completed": list(self.completed),
            "remaining": list(self.remaining),
            "confidence": self.confidence,
            "termination_reason": self.termination_reason,
        }


__all__ = ["TaskProgress"]
