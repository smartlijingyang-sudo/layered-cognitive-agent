"""plan_ref × Journal 绑定（ADR-0074 PR-6）。

每条 journal fact 必须携带 ``plan_ref``（来自 CompiledRunPlan）；PR-6 实现：

1. ``plan_ref: str`` 字段写入 ``StampedEvent``（每个 stamped event 自带）
2. ``_run_plan_ref`` ContextVar — 当前 run 关联的 plan_ref
3. ``set_current_plan_ref(plan_ref)`` / ``get_current_plan_ref()`` /
   ``reset_current_plan_ref()`` 模块级 helpers
4. ``RunStore.append()`` 自动从 ContextVar 读取并盖章 plan_ref
5. ``EventDescriptorRegistry.require()`` 校验 ``plan_ref_required`` 字段

replay test 守护（acceptance-criteria §3.3 V5）：

- 跑 1 个完整 agent run
- 取 journal 全量 facts
- 断言每条 fact 携带 plan_ref
- 断言取任意 plan_ref 可重放该 plan 的 CapabilityPlan、声明式控制投影与 ScopePlan

设计原则：

- plan_ref 通过 ContextVar 注入而非 kwargs — 与 ``get_current_run_scope()``
  模式一致（journal.py 已用 ContextVar 注入关联骨架）
- 不破坏现有 JournalEvent / StampedEvent 类型 — plan_ref 是 StampedEvent
  新字段，journal fact dataclass 不变
- 兼容：未 set plan_ref 的 legacy code path → append 空字符串 ``""``（不阻塞）
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# 计划关联 plan_ref：与 RunScope 同源（ContextVar）；null/empty = 未关联 plan
_run_plan_ref: ContextVar[str] = ContextVar("lca_run_plan_ref", default="")


def get_current_plan_ref() -> str:
    """读取当前 run 关联的 plan_ref（PR-6 ContextVar）。

    未设置返回空字符串 ``""``（legacy path：与 plan 无关联的代码）。
    """
    return _run_plan_ref.get()


def set_current_plan_ref(plan_ref: str) -> object:
    """设置当前 run 关联的 plan_ref。返回 ``Token`` 用于 ``reset_current_plan_ref``。

    ``plan_ref`` 必须非空字符串（PR-6 防御：避免误设置空 plan_ref 覆盖
    上层 plan_ref）。空字符串 → ValueError。
    """
    if not plan_ref:
        raise ValueError(
            "set_current_plan_ref: plan_ref must be non-empty string "
            "(use reset_current_plan_ref to clear)"
        )
    return _run_plan_ref.set(plan_ref)


def reset_current_plan_ref(token: object) -> None:
    """Reset ContextVar to prior state（``set_current_plan_ref`` 返回的 token）。"""
    _run_plan_ref.reset(token)  # type: ignore[arg-type]


@contextmanager
def plan_ref_scope(plan_ref: str) -> Iterator[str]:
    """Context manager：在 with 块内 plan_ref 自动 active，退出时 reset。

    用法：

    .. code-block:: python

        with plan_ref_scope("abc123"):
            # 所有 append 自动盖章 plan_ref="abc123"
            run_store.append(event)
    """
    token = set_current_plan_ref(plan_ref)
    try:
        yield plan_ref
    finally:
        reset_current_plan_ref(token)


def stamped_event_has_plan_ref(plan_ref: str) -> bool:
    """``StampedEvent.plan_ref`` 非空检查（PR-6 V5 验收守护）。

    用于 replay test / architecture test。
    """
    return bool(plan_ref)


__all__ = [
    "get_current_plan_ref",
    "plan_ref_scope",
    "reset_current_plan_ref",
    "set_current_plan_ref",
    "stamped_event_has_plan_ref",
]
