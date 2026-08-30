"""Typed factories for declaratively assembled runtime mechanisms.

The runtime kernel owns the non-bypassable transaction order.  Profiles select
how the individual seams are created through these factories, so composition
does not reconstruct concrete registry-backed implementations in L2.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from lca.contracts.mechanisms import HookRegistry
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.artifact_closure import ArtifactClosure
from lca.contracts.protocols.declarative_phase_graph import (
    DeltaReducer,
    EffectGateway,
    JournalCommitter,
)
from lca.contracts.protocols.delta_handler import DeltaHandlerRegistry
from lca.contracts.protocols.effect_handler import EffectCapabilities, EffectHandlerRegistry
from lca.contracts.protocols.idempotency import IdempotencyStore
from lca.contracts.protocols.infra import StateStore
from lca.contracts.protocols.reducer import Reducer
from lca.contracts.protocols.runtime import Runtime
from lca.contracts.protocols.runtime_lifecycle import RuntimeLifecyclePublisher


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
    The two properties nevertheless enforce the required asynchronous fresh-run
    and resume entry points without coupling alternative implementations to the
    default interpreter's internal carrier types.
    """

    @property
    def run(self) -> Callable[..., Awaitable[object]]: ...

    @property
    def resume(self) -> Callable[..., Awaitable[object]]: ...


@runtime_checkable
class DeclarativeInterpreterFactory(Protocol):
    """Create the profile-selected phase-graph traversal implementation."""

    def create(
        self,
        *,
        journal: RuntimeJournal,
        effect_gateway: EffectGateway,
        reducer: DeltaReducer,
        phase_observer: object,
        lifecycle_publisher: RuntimeLifecyclePublisher,
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
class EffectGatewayFactory(Protocol):
    """Create the selected policy-governed effect execution gateway."""

    def create(
        self,
        *,
        capabilities: EffectCapabilities,
        effect_handler_registry: EffectHandlerRegistry,
        idempotency_store: IdempotencyStore,
    ) -> EffectGateway: ...


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
    "EffectGatewayFactory",
    "ResultFinalizer",
    "ResultFinalizerFactory",
    "RuntimeFactory",
    "RuntimeJournal",
    "RuntimeJournalFactory",
]
