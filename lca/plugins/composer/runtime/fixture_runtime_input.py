"""Explicit fixture inputs for exercising the production runtime closure.

This module deliberately contains data only. Fixture defaults and the translation
into production bindings belong to ``fixture_runtime_adapter`` so callers can see
where the test-only adaptation seam lives.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from lca.contracts.mechanisms import HookRegistry
from lca.contracts.protocols import (
    ArtifactClosure,
    Body,
    Brain,
    MemorySystem,
    PerceiveHub,
    Reducer,
    StateStore,
    StopPolicy,
)
from lca.contracts.protocols.act.effect_handler import EffectHandlerRegistry
from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseExecutor
from lca.contracts.protocols.journal.idempotency import IdempotencyStore
from lca.contracts.protocols.runtime.runtime_composition import (
    CheckpointStateResolverFactory,
    DeclarativeInterpreterFactory,
    DeltaReducerFactory,
    EffectGatewayFactory,
    ResultFinalizerFactory,
    RuntimeJournalFactory,
)
from lca.contracts.protocols.session.resume_input import ResumeInputAdapter
from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
from lca.contracts.protocols.state.plan import CompiledRunPlan
from lca.harness.declarative.phase_observation import PhaseObserver, TracingPhaseObserver


@dataclass(frozen=True, slots=True)
class RuntimeDeps:
    """Partial fixture input; no defaulting or production translation is owned here."""

    brain: Brain
    body: Body
    memory: MemorySystem
    hooks: HookRegistry
    state_store: StateStore
    perceive_hub: PerceiveHub
    phase_capabilities: Mapping[str, object]
    stop_policy: StopPolicy | None = None
    reducer: Reducer | None = None
    compiled_plan: CompiledRunPlan | None = None
    phase_executors: Mapping[str, PhaseExecutor] = field(default_factory=dict)
    effect_handler_registry: EffectHandlerRegistry | None = None
    delta_handler_registry: DeltaHandlerRegistry | None = None
    artifact_closure: ArtifactClosure | None = None
    idempotency_store: IdempotencyStore | None = None
    resume_input_adapter: ResumeInputAdapter | None = None
    effect_gateway_factory: EffectGatewayFactory | None = None
    delta_reducer_factory: DeltaReducerFactory | None = None
    journal_factory: RuntimeJournalFactory | None = None
    interpreter_factory: DeclarativeInterpreterFactory | None = None
    checkpoint_state_resolver_factory: CheckpointStateResolverFactory | None = None
    result_finalizer_factory: ResultFinalizerFactory | None = None
    phase_observer: PhaseObserver = field(default_factory=TracingPhaseObserver)


__all__ = ["RuntimeDeps"]
