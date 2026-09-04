"""声明式计划解释器所使用的稳定执行 wire shape 与协议。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Protocol, runtime_checkable

from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.core.stop import StopDecision
from lca.contracts.protocols.act.command_envelope import CommandEnvelope, RunDelta, RunFact
from lca.contracts.protocols.declarative.declarative_common import DeclarativeValidationError
from lca.contracts.protocols.declarative.declarative_graph import EffectPolicyPlan


@runtime_checkable
class PhaseCapabilityReader(Protocol):
    """Read only the capabilities declared for one phase execution scope.

    Phase executors cannot discover services from a live Cordis context. They can
    only ask for a named capability that the composition layer deliberately
    placed in this narrow view.
    """

    def get(self, name: str) -> object | None: ...

    def require(self, name: str) -> object: ...


class StandardPhaseCapability(str, Enum):
    """Closed names exposed to built-in phase executors."""

    BRAIN = "brain"
    BODY = "body"
    MEMORY = "memory"
    PERCEIVE_HUB = "perceive_hub"
    STOP_POLICY = "stop_policy"


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


@dataclass(frozen=True, slots=True)
class PhaseInput:
    artifact: object | None = None
    causation_refs: tuple[str, ...] = ()


PhaseErrorCategory = Literal["timeout", "transient", "permanent"]


# Outer phase error kind (ADR-clean-truths 决策 一).
# 区别于 PhaseErrorCategory（attempt 内部失败分类）,
# 这里表达的是 PhaseExecutionFailure 这个 boundary 事件的根因。
# UI / LobeHub / run-doctor 只读 error_kind,不再拼接文学化 message。
PhaseErrorKind = Literal[
    "timeout",  # wait_for / asyncio timeout
    "contract",  # 类型/参数/状态 contract violation
    "cancelled",  # 上层取消
    "provider",  # LLM/provider 上游故障
    "internal",  # 未分类内部错误
]


def _derive_error_kind(attempts: tuple[PhaseAttemptFailure, ...]) -> str:
    """从最后一次 attempt 的 category 推导 outer error_kind。

    PhaseErrorCategory 与 PhaseErrorKind 的映射:
      timeout   → timeout
      transient → provider
      permanent → internal（永久错误被默认视为契约/语义错误,除非显式归类）
    """
    if not attempts:
        return "internal"
    last_category = attempts[-1].category
    if last_category == "timeout":
        return "timeout"
    if last_category == "transient":
        return "provider"
    return "internal"


@dataclass(frozen=True, slots=True)
class PhaseAttemptFailure:
    """Sanitized, replay-safe metadata for one failed phase attempt."""

    attempt: int
    category: PhaseErrorCategory
    error_type: str


@dataclass(frozen=True, slots=True)
class PhaseExecutionFailure:
    """Typed payload emitted when a phase exhausts its attempt policy."""

    node_id: str
    attempts: tuple[PhaseAttemptFailure, ...]
    last_tool_call_id: str | None = None
    # ADR-clean-truths 决策 一:PhaseExecutionFailure 自身携带结构化错误分类,
    # 下游不再依赖 message 字符串里的"the agent could not complete a required
    # {node_id} step after {n} attempt(s)"这种文学化叙述。默认从 attempts[-1]
    # 推导(timeout → "timeout",transient → "provider",其他 → "internal"),
    # 显式传入可覆盖。
    error_kind: PhaseErrorKind = ""

    def __post_init__(self) -> None:
        if not self.node_id:
            raise DeclarativeValidationError("PG-010", "phase execution failure requires a node id")
        if not isinstance(self.attempts, tuple):
            object.__setattr__(self, "attempts", tuple(self.attempts))
        if not self.attempts:
            raise DeclarativeValidationError(
                "PG-010", "phase execution failure requires at least one attempt"
            )
        if not self.error_kind:
            object.__setattr__(self, "error_kind", _derive_error_kind(self.attempts))

    def is_retryable(self) -> bool:
        """外部策略可读的最小信号:是否值得重试。"""
        return self.error_kind in ("timeout", "provider")


@dataclass(frozen=True, slots=True)
class PhaseResult:
    """PhaseExecutor 的唯一标准返回值。"""

    result_kind: str
    facts: tuple[RunFact, ...] = ()
    deltas: tuple[RunDelta, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    next_hints: Mapping[str, object] = field(default_factory=dict)
    payload: object | None = None
    command_envelope: CommandEnvelope | None = None

    def __post_init__(self) -> None:
        if not self.result_kind:
            raise DeclarativeValidationError("RT-002", "PhaseResult.result_kind must be non-empty")
        if not isinstance(self.facts, tuple):
            object.__setattr__(self, "facts", tuple(self.facts))
        if not isinstance(self.deltas, tuple):
            object.__setattr__(self, "deltas", tuple(self.deltas))
        if not isinstance(self.evidence_refs, tuple):
            object.__setattr__(
                self, "evidence_refs", tuple(str(item) for item in self.evidence_refs)
            )
        if not isinstance(self.next_hints, Mapping):
            object.__setattr__(self, "next_hints", dict(self.next_hints))


@runtime_checkable
class PhaseContext(Protocol):
    """插件可见的只读执行上下文；不暴露 Cordis Context。"""

    plan_ref: str
    node_ref: str
    state: AgentState
    journal: JournalCommitter
    budget: Budget
    artifacts: Mapping[str, object]
    capabilities: PhaseCapabilityReader
    decision: Decision | None
    observation: Observation | None
    reflection: Reflection | None
    checkpoint_reason: str | None

    def emit_fact(self, fact: RunFact) -> str: ...

    def propose_delta(self, delta: RunDelta) -> None: ...


@runtime_checkable
class PhaseExecutor(Protocol):
    async def execute(self, context: PhaseContext, input: PhaseInput) -> PhaseResult: ...


@runtime_checkable
class EffectDispatcher(Protocol):
    async def execute(self, envelope: CommandEnvelope, policy: EffectPolicyPlan) -> object: ...


@runtime_checkable
class JournalCommitter(Protocol):
    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> str: ...

    def commit_evidence(self, evidence_ref: str, *, plan_ref: str, node_ref: str) -> str: ...

    def commit_observation(self, observation: object, *, plan_ref: str, node_ref: str) -> str: ...


@runtime_checkable
class DeltaReducer(Protocol):
    def apply_delta(self, state: AgentState, delta: RunDelta) -> AgentState: ...


__all__ = [
    "DeclarativeRunOutcome",
    "DeltaReducer",
    "EffectDispatcher",
    "ExecutionOutcome",
    "JournalCommitter",
    "PhaseAttemptFailure",
    "PhaseCapabilityReader",
    "PhaseContext",
    "PhaseErrorCategory",
    "PhaseErrorKind",
    "PhaseExecutionFailure",
    "PhaseExecutor",
    "PhaseInput",
    "PhaseResult",
    "PhaseRunCursor",
    "StandardPhaseCapability",
]
