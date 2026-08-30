"""声明式计划解释器所使用的稳定执行 wire shape 与协议。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Protocol, runtime_checkable

from lca.contracts.models.core.decision import Decision, Observation, Reflection
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.core.stop import StopDecision
from lca.contracts.protocols.command_envelope import CommandEnvelope, RunDelta, RunFact
from lca.contracts.protocols.declarative_common import DeclarativeValidationError
from lca.contracts.protocols.declarative_graph import EffectPolicyPlan


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


@dataclass(frozen=True, slots=True)
class DeclarativeRunOutcome:
    """完成、暂停、失败或效果不确定时的统一运行结果。"""

    kind: Literal["completed", "paused", "failed", "effect_uncertain"]
    cursor: PhaseRunCursor
    stop: StopDecision
    error_fact: RunFact | None = None
    approval_request: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"completed", "paused", "failed", "effect_uncertain"}:
            raise DeclarativeValidationError(
                "PG-009",
                "outcome kind must be one of: completed, paused, failed, effect_uncertain; "
                f"got {self.kind!r}",
            )
        if not isinstance(self.cursor, PhaseRunCursor):
            raise DeclarativeValidationError("PG-009", "outcome must carry a PhaseRunCursor")


@dataclass(frozen=True, slots=True)
class PhaseInput:
    artifact: object | None = None
    causation_refs: tuple[str, ...] = ()


PhaseErrorCategory = Literal["timeout", "transient", "permanent"]


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

    def __post_init__(self) -> None:
        if not self.node_id:
            raise DeclarativeValidationError("PG-010", "phase execution failure requires a node id")
        if not isinstance(self.attempts, tuple):
            object.__setattr__(self, "attempts", tuple(self.attempts))
        if not self.attempts:
            raise DeclarativeValidationError(
                "PG-010", "phase execution failure requires at least one attempt"
            )


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
class EffectGateway(Protocol):
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
    "EffectGateway",
    "JournalCommitter",
    "PhaseAttemptFailure",
    "PhaseCapabilityReader",
    "PhaseContext",
    "PhaseErrorCategory",
    "PhaseExecutionFailure",
    "PhaseExecutor",
    "PhaseInput",
    "PhaseResult",
    "PhaseRunCursor",
    "StandardPhaseCapability",
]
