"""声明式计划解释器所使用的稳定执行 wire shape 与协议。

ADR-0221: PhaseExecutor / PhaseInput / PhaseResult / PhaseContext /
PhaseExecutionFailure / PhaseCapabilityReader / StandardPhaseCapability
have been retired. Every phase node is a :class:`NodeExecutor` (see
``declarative_1.node_executor``); upstream typed product propagation
goes through :class:`NodeInput.port_values` and ``results_by_phase`` is
no longer needed (the kernel passes the typed port map directly).

This module keeps the surviving cross-cutting contracts:
:data:`ExecutionOutcome`, :class:`DeclarativeRunOutcome`,
:class:`PhaseRunCursor`, :class:`DeltaReducer`, :class:`EffectDispatcher`,
:class:`JournalCommitter`. They are still consumed by the kernel's
typed interpretation result and by the runtime bindings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from lca.contracts.models.core.policy.stop import StopDecision
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.act.command.envelope import CommandEnvelope, RunDelta, RunFact
from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import EffectPolicyPlan


@dataclass(frozen=True, slots=True)
class PhaseRunCursor:
    """可持久化的阶段运行游标，不包含 live Context 引用。"""

    plan_ref: str
    node_id: str
    visit_counts: tuple[tuple[str, int], ...]
    edge_counts: tuple[tuple[str, str, int], ...]
    artifacts: dict[str, object]
    causation_refs: tuple[str, ...]
    budget_snapshot: dict[str, int]

    def __post_init__(self) -> None:
        if not self.plan_ref:
            raise DeclarativeValidationError("PG-008", "cursor plan_ref must be non-empty")
        if not self.node_id:
            raise DeclarativeValidationError("PG-008", "cursor node_id must be non-empty")
        if not isinstance(self.visit_counts, tuple):
            object.__setattr__(self, "visit_counts", tuple(self.visit_counts))
        if not isinstance(self.edge_counts, tuple):
            object.__setattr__(self, "edge_counts", tuple(self.edge_counts))
        if not isinstance(self.causation_refs, tuple):
            object.__setattr__(self, "causation_refs", tuple(self.causation_refs))


class ExecutionOutcome(str, Enum):
    """声明式单次执行结果闭集(收敛契约 note-1:与 ``RunLifecycleStatus`` 不合并)。

    语义边界:``RunLifecycleStatus`` 是 run 生命周期状态;本 enum 是
    step / phase / declarative 单次执行的结果。``DeclarativeRunOutcome``
    不序列化 ``kind``,成员值仅用于进程内比较与投影分支。
    """

    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"
    EFFECT_UNCERTAIN = "effect_uncertain"


@dataclass(frozen=True, slots=True)
class DeclarativeRunOutcome:
    """完成、暂停、失败或效果不确定时的统一运行结果。"""

    kind: ExecutionOutcome
    cursor: PhaseRunCursor
    stop: StopDecision
    error_fact: RunFact | None = None
    approval_request: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ExecutionOutcome):
            try:
                object.__setattr__(self, "kind", ExecutionOutcome(self.kind))
            except ValueError:
                raise DeclarativeValidationError(
                    "PG-009",
                    "outcome kind must be one of: completed, paused, failed, effect_uncertain; "
                    f"got {self.kind!r}",
                ) from None
        if not isinstance(self.cursor, PhaseRunCursor):
            raise DeclarativeValidationError("PG-009", "outcome must carry a PhaseRunCursor")


class DeltaReducer(Protocol):
    """Runtime Protocol for delta application — concrete impl lives at runtime_bindings."""


class EffectDispatcher(Protocol):
    """Runtime Protocol for effect dispatch — concrete impl lives at runtime_bindings."""


@runtime_checkable
class JournalCommitter(Protocol):
    """Runtime Protocol for journal commits — concrete impl lives at runtime_bindings."""


__all__ = [
    "DeclarativeRunOutcome",
    "DeltaReducer",
    "EffectDispatcher",
    "ExecutionOutcome",
    "JournalCommitter",
    "PhaseRunCursor",
]
