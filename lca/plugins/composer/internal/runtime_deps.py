"""Explicit production runtime dependency closure.

This module owns the dependency value that crosses from graph composition into
runtime binding. It deliberately does not assemble a runtime or resolve scope
capabilities; those responsibilities belong to the neighboring composition
modules.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from lca.contracts.mechanisms import HookRegistry
from lca.contracts.protocols import (
    ArtifactClosure,
    Body,
    Brain,
    MemorySystem,
    PerceiveHub,
    Reducer,
    StateStore,
)
from lca.contracts.protocols.declarative_phase_graph import PhaseExecutor
from lca.contracts.protocols.delta_handler import DeltaHandlerRegistry
from lca.contracts.protocols.effect_handler import EffectHandlerRegistry
from lca.contracts.protocols.idempotency import IdempotencyStore
from lca.contracts.protocols.plan import CompiledRunPlan
from lca.contracts.protocols.resume_input import ResumeInputAdapter
from lca.contracts.protocols.runtime_composition import (
    CheckpointStateResolverFactory,
    DeclarativeInterpreterFactory,
    DeltaReducerFactory,
    EffectGatewayFactory,
    ResultFinalizerFactory,
    RuntimeJournalFactory,
)
from lca.contracts.protocols.runtime_lifecycle import RuntimeLifecyclePublisher
from lca.harness.declarative.phase_observation import PhaseObserver
from lca.runtime.phase_capabilities import (
    RuntimePhaseCapabilities,
    project_runtime_phase_capabilities,
)


@dataclass(frozen=True)
class ProductionRuntimeDeps:
    """The complete, explicit closure accepted by production runtime binding.

    Cognitive facts are canonical inputs. The phase capability map may contain
    them for callers that already assembled a graph, but conflicting duplicates
    are rejected by the canonical projection below.
    """

    brain: Brain
    body: Body
    memory: MemorySystem
    hooks: HookRegistry
    state_store: StateStore
    perceive_hub: PerceiveHub
    reducer: Reducer
    compiled_plan: CompiledRunPlan
    phase_executors: Mapping[str, PhaseExecutor]
    phase_capabilities: Mapping[str, object]
    effect_handler_registry: EffectHandlerRegistry
    delta_handler_registry: DeltaHandlerRegistry
    artifact_closure: ArtifactClosure
    idempotency_store: IdempotencyStore
    resume_input_adapter: ResumeInputAdapter
    effect_gateway_factory: EffectGatewayFactory
    delta_reducer_factory: DeltaReducerFactory
    journal_factory: RuntimeJournalFactory
    interpreter_factory: DeclarativeInterpreterFactory
    checkpoint_state_resolver_factory: CheckpointStateResolverFactory
    result_finalizer_factory: ResultFinalizerFactory
    phase_observer: PhaseObserver
    lifecycle_publisher: RuntimeLifecyclePublisher | None = None

    def runtime_phase_capabilities(self) -> RuntimePhaseCapabilities:
        """Project one frozen phase view from the canonical graph facts."""
        return project_runtime_phase_capabilities(
            phase_capabilities=self.phase_capabilities,
            brain=self.brain,
            body=self.body,
            memory=self.memory,
            perceive_hub=self.perceive_hub,
        )


__all__ = ["ProductionRuntimeDeps"]
