"""Adapt partial fixture inputs to the production runtime dependency closure.

The adapter owns test-only defaults and the one-way translation into
``ProductionRuntimeDeps``. Keeping this policy out of the input dataclass makes
the fixture data model a stable test seam and prevents it from becoming a second
runtime assembly path.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from lca.contracts.protocols import (
    ArtifactClosure,
    Reducer,
)
from lca.contracts.protocols.act.effect_handler import EffectHandlerRegistry
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
from lca.harness.declarative.execute.loop_guard import DeclarativeLoopGuardEvaluator
from lca.plugins.composer.runtime import fixture_runtime_defaults
from lca.plugins.composer.runtime.fixture_runtime_input import RuntimeDeps
from lca.plugins.composer.runtime.runtime_deps import ProductionRuntimeDeps
from lca.plugins.phase_graph.stop_policy import DefaultStopPolicy
from lca.plugins.providers.journal.declarative_runtime_seams import (
    DefaultCheckpointStateResolverFactory,
    DefaultDeclarativeInterpreterFactory,
    DefaultResultFinalizerFactory,
    ObservabilityRuntimeJournalFactory,
    RegistryDeltaReducerFactory,
    RegistryEffectGatewayFactory,
)
from lca.runtime.reducer import DefaultReducer


class FixtureRuntimeAdapter:
    """Own fixture completion and its translation into production dependencies."""

    def __init__(self, deps: RuntimeDeps) -> None:
        self._deps = deps

    def complete(self) -> RuntimeDeps:
        """Complete only the mechanisms that are intentionally fixture-local."""

        artifact_closure = (
            self._deps.artifact_closure or fixture_runtime_defaults.artifact_closure()
        )
        stop_policy = self._deps.stop_policy or DefaultStopPolicy(artifact_closure)
        phase_capabilities = {**self._deps.phase_capabilities, "stop_policy": stop_policy}
        return replace(
            self._deps,
            phase_capabilities=phase_capabilities,
            stop_policy=stop_policy,
            reducer=self._deps.reducer or DefaultReducer(),
            effect_handler_registry=self._deps.effect_handler_registry
            or fixture_runtime_defaults.effect_handlers(),
            delta_handler_registry=self._deps.delta_handler_registry
            or fixture_runtime_defaults.delta_handlers(),
            artifact_closure=artifact_closure,
            idempotency_store=self._deps.idempotency_store
            or fixture_runtime_defaults.idempotency_store(),
            resume_input_adapter=self._deps.resume_input_adapter
            or fixture_runtime_defaults.resume_input_adapter(),
            effect_gateway_factory=self._deps.effect_gateway_factory
            or RegistryEffectGatewayFactory(),
            delta_reducer_factory=self._deps.delta_reducer_factory or RegistryDeltaReducerFactory(),
            journal_factory=self._deps.journal_factory or ObservabilityRuntimeJournalFactory(),
            interpreter_factory=self._deps.interpreter_factory
            or DefaultDeclarativeInterpreterFactory(DeclarativeLoopGuardEvaluator()),
            checkpoint_state_resolver_factory=self._deps.checkpoint_state_resolver_factory
            or DefaultCheckpointStateResolverFactory(),
            result_finalizer_factory=self._deps.result_finalizer_factory
            or DefaultResultFinalizerFactory(),
        )

    def to_production_runtime_deps(self) -> ProductionRuntimeDeps:
        """Translate the completed fixture input through the production seam."""

        resolved = self.complete()
        return ProductionRuntimeDeps(
            brain=resolved.brain,
            body=resolved.body,
            memory=resolved.memory,
            hooks=resolved.hooks,
            state_store=resolved.state_store,
            perceive_hub=resolved.perceive_hub,
            reducer=cast("Reducer", resolved.reducer),
            compiled_plan=cast("CompiledRunPlan", resolved.compiled_plan),
            phase_executors=resolved.phase_executors,
            phase_capabilities=resolved.phase_capabilities,
            effect_handler_registry=cast("EffectHandlerRegistry", resolved.effect_handler_registry),
            delta_handler_registry=cast("DeltaHandlerRegistry", resolved.delta_handler_registry),
            artifact_closure=cast("ArtifactClosure", resolved.artifact_closure),
            idempotency_store=cast("IdempotencyStore", resolved.idempotency_store),
            resume_input_adapter=cast("ResumeInputAdapter", resolved.resume_input_adapter),
            effect_gateway_factory=cast("EffectGatewayFactory", resolved.effect_gateway_factory),
            delta_reducer_factory=cast("DeltaReducerFactory", resolved.delta_reducer_factory),
            journal_factory=cast("RuntimeJournalFactory", resolved.journal_factory),
            interpreter_factory=cast("DeclarativeInterpreterFactory", resolved.interpreter_factory),
            checkpoint_state_resolver_factory=cast(
                "CheckpointStateResolverFactory",
                resolved.checkpoint_state_resolver_factory,
            ),
            result_finalizer_factory=cast(
                "ResultFinalizerFactory",
                resolved.result_finalizer_factory,
            ),
            phase_observer=resolved.phase_observer,
        )


__all__ = ["FixtureRuntimeAdapter"]
