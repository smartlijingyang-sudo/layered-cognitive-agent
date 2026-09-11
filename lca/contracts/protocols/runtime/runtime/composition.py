"""Typed factories for declaratively assembled runtime mechanisms.

The runtime kernel owns the non-bypassable transaction order.  Profiles select
how the individual seams are created through these factories, so composition
does not reconstruct concrete registry-backed implementations in L2.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from lca.contracts.mechanisms import HookRegistry
from lca.contracts.models.core.execution.result import Result
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.act.effect.handler import EffectCapabilities, EffectHandlerRegistry
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    DeltaReducer,
    EffectDispatcher,
    JournalCommitter,
)

if TYPE_CHECKING:
    from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
        PhaseExecutor,
    )
    from lca.contracts.protocols.declarative.declarative_1.node_executor import (
        NodeExecutor,
    )
from lca.contracts.protocols.journal.artifact.closure import ArtifactClosure
from lca.contracts.protocols.journal.idempotency.idempotency import IdempotencyStore
from lca.contracts.protocols.runtime.infra.infra import StateStore
from lca.contracts.protocols.runtime.runtime.lifecycle import RuntimeLifecyclePublisher
from lca.contracts.protocols.runtime.runtime.runtime import Runtime
from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
from lca.contracts.protocols.state.reducer import Reducer


@runtime_checkable
class RuntimeFactory(Protocol):
    """Build one profile-selected runtime from immutable declarative bindings.

    The factory is the sole composition seam allowed to choose a concrete loop
    implementation.  Its input and output intentionally remain opaque at the
    contracts layer so L2 runtime implementations never leak upward into the
    shared protocol package.
    """

    def create(self, bindings: object) -> Runtime: ...


@runtime_checkable
class RuntimeJournal(JournalCommitter, Protocol):
    """A per-turn journal with a stable sequence for terminal outcomes."""

    @property
    def sequence(self) -> int: ...


@runtime_checkable
class RuntimeJournalFactory(Protocol):
    """Create an isolated journal for each fresh or resumed turn."""

    def create(self) -> RuntimeJournal: ...


@runtime_checkable
class DeclarativeInterpreter(Protocol):
    """Execute a previously assembled declarative phase graph.

    Graph, state, and outcome carriers remain opaque at the composition boundary.
    ``run`` / ``resume`` are async callables; ``lca.loop.driver`` and the run-loop
    call them as bound methods (e.g. ``await interpreter.run(executable, ...)``),
    so this Protocol must declare methods, not properties.
    """

    async def run(self, executable: object, **kwargs: object) -> object: ...

    async def resume(self, executable: object, **kwargs: object) -> object: ...


@runtime_checkable
class DeclarativeInterpreterFactory(Protocol):
    """Create the profile-selected phase-graph traversal implementation.

    ``graph_observer`` and ``graph_clock`` are optional wiring knobs that
    let production runs stream :class:`lca.framework.graph.observation.GraphObservation`
    events to the spine while unit tests and fixture adapters stay
    decoupled from the EventSpine surface. Default factories accept
    ``None`` and forward to ``PlanInterpreterAdapter``'s NullGraphObserver
    + monotonic millisecond clock fallback.
    """

    def create(
        self,
        *,
        journal: RuntimeJournal,
        effect_gateway: EffectDispatcher,
        reducer: DeltaReducer,
        phase_observer: object,
        lifecycle_publisher: RuntimeLifecyclePublisher,
        phase_executors: Mapping[str, PhaseExecutor] | None = None,
        phase_capabilities: object | None = None,
        node_executors: Mapping[str, NodeExecutor] | None = None,
        node_executor_runtime_scope: object | None = None,
        graph_observer: object | None = None,
        graph_clock: Callable[[], int] | None = None,
    ) -> DeclarativeInterpreter: ...


@runtime_checkable
class CheckpointStateResolver(Protocol):
    """Restore a checkpoint into the state that declarative execution can resume."""

    async def resolve(self, checkpoint: object, *, expected_plan_ref: str) -> AgentState: ...


@runtime_checkable
class CheckpointStateResolverFactory(Protocol):
    """Create the profile-selected resolver for durable resume checkpoints."""

    def create(self, *, state_store: StateStore) -> CheckpointStateResolver: ...


@runtime_checkable
class ResultFinalizer(Protocol):
    """Fold terminal interpretation facts and return a carrier-safe result."""

    async def finalize(
        self,
        *,
        interpretation: object,
        plan_ref: str,
        journal_sequence: int,
    ) -> Result: ...


@runtime_checkable
class ResultFinalizerFactory(Protocol):
    """Create the profile-selected terminal folding and carrier-projection seam."""

    def create(
        self,
        *,
        reducer: Reducer,
        hooks: HookRegistry,
        artifact_closure: ArtifactClosure,
        state_store: StateStore,
    ) -> ResultFinalizer: ...


@runtime_checkable
class EffectDispatcherFactory(Protocol):
    """Create the selected policy-governed effect execution gateway."""

    def create(
        self,
        *,
        capabilities: EffectCapabilities,
        effect_handler_registry: EffectHandlerRegistry,
        idempotency_store: IdempotencyStore,
    ) -> EffectDispatcher: ...


@runtime_checkable
class DeltaReducerFactory(Protocol):
    """Create the selected single-writer adapter for declared state deltas."""

    def create(
        self,
        *,
        reducer: Reducer,
        delta_handler_registry: DeltaHandlerRegistry,
    ) -> DeltaReducer: ...


__all__ = [
    "CheckpointStateResolver",
    "CheckpointStateResolverFactory",
    "DeclarativeInterpreter",
    "DeclarativeInterpreterFactory",
    "DeltaReducerFactory",
    "EffectDispatcherFactory",
    "ResultFinalizer",
    "ResultFinalizerFactory",
    "RuntimeFactory",
    "RuntimeJournal",
    "RuntimeJournalFactory",
]
