"""Run scope ContextVar management — ambient correlation identity.

This module owns the ``ContextVar`` that tracks the current ``RunScope``
across async task boundaries. Extracted from ``contracts/models/observability/journal.py``
per ADR-0015 (contracts contain pure data, not ambient state management).

The journal event vocabulary (``RunScope``, ``JournalEvent``, etc.) remains
in contracts; this module provides the runtime mechanism for accessing the
current correlation context.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from lca.contracts.atoms.ids import new_run_id, new_trace_id
from lca.contracts.models.observability.journal import RunScope

__all__ = [
    "TEAM_CONTAINER_ROLE",
    "adopt_run_scope",
    "get_current_run_scope",
    "run_scope",
]

_run_scope: ContextVar[RunScope | None] = ContextVar("lca_run_scope", default=None)

TEAM_CONTAINER_ROLE = "team"


def get_current_run_scope() -> RunScope | None:
    """读取当前 run 关联身份；未设置返回 None（solo 且未入 run 边界）。"""
    return _run_scope.get()


def adopt_run_scope(*, role: str) -> tuple[RunScope, bool]:
    """Claim an allocated root Run, or mint a child / new root.

    Gateway (and tests) may open ``RunScope(run_id=..., agent_role='')`` before
    ``Agent`` / ``Team``.run. The first actor claims that id. Nested actors
    (delegation, another speaker) mint a child. Returns ``(scope, is_root)``.

    使用品牌化 ID 工厂：trace_id 和 run_id 在类型层面区分，
    防止关联骨架 ID 混传。
    """
    inherited = get_current_run_scope()
    if inherited is None:
        return RunScope(trace_id=new_trace_id(), run_id=new_run_id(), agent_role=role), True
    claimed = bool(inherited.agent_role)
    if (
        inherited.run_id
        and not inherited.parent_run_id
        and not inherited.delegation_id
        and not claimed
    ):
        return (
            RunScope(trace_id=inherited.trace_id, run_id=inherited.run_id, agent_role=role),
            True,
        )
    return (
        RunScope(
            trace_id=inherited.trace_id,
            run_id=new_run_id(),
            parent_run_id=inherited.run_id or inherited.parent_run_id,
            delegation_id=inherited.delegation_id,
            agent_role=role,
        ),
        False,
    )


@contextmanager
def run_scope(scope: RunScope) -> Iterator[None]:
    """在 run 边界包裹此上下文：asyncio.create_task 拷贝 Context 后，
    成员任务读到的是发起方的关联身份（与 delegator_scope 同一机制）。"""
    token = _run_scope.set(scope)
    try:
        yield
    finally:
        _run_scope.reset(token)
