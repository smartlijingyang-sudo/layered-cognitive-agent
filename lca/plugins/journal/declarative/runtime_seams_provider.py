"""Default factories for declaratively selected runtime execution seams.

These factories preserve the existing registry-backed behavior while moving its
concrete construction out of ``DeclarativeRuntimeBindings``.  A profile can
replace any factory capability without changing the runtime kernel.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.protocols.act.effect.handler import EffectCapabilities, EffectHandlerRegistry
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    DeltaReducer,
    EffectDispatcher,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.journal.artifact.closure import ArtifactClosure
from lca.contracts.protocols.journal.idempotency.idempotency import IdempotencyStore
from lca.contracts.protocols.runtime.infra.infra import StateStore
from lca.contracts.protocols.runtime.runtime.composition import (
    CheckpointStateResolver,
    CheckpointStateResolverFactory,
    DeclarativeInterpreter,
    DeclarativeInterpreterFactory,
    DeltaReducerFactory,
    EffectDispatcherFactory,
    ResultFinalizer,
    ResultFinalizerFactory,
    RuntimeJournal,
    RuntimeJournalFactory,
)
from lca.contracts.protocols.runtime.runtime.lifecycle import RuntimeLifecyclePublisher
from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
from lca.contracts.protocols.state.reducer import Reducer
from lca.framework.graph.adapter import PlanInterpreterAdapter
from lca.harness.declarative.execute.dispatch import RegistryDeltaReducer, RegistryEffectDispatcher
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.runtime.loop.runtime_journal import RuntimeJournalCommitter
from lca.runtime.projection.result_finalizer import RuntimeResultFinalizer
from lca.runtime.support.checkpoint_resolution import DeclarativeCheckpointStateResolver


class Config(BaseModel):
    """Default declarative runtime-factory configuration."""

    model_config = {"extra": "forbid"}


class RegistryEffectDispatcherFactory(EffectDispatcherFactory):
    """Create the standard policy and idempotency governed effect gateway."""

    def create(
        self,
        *,
        capabilities: EffectCapabilities,
        effect_handler_registry: EffectHandlerRegistry,
        idempotency_store: IdempotencyStore,
    ) -> EffectDispatcher:
        return RegistryEffectDispatcher(
            capabilities,
            effect_handler_registry,
            idempotency_store,
        )


class RegistryDeltaReducerFactory(DeltaReducerFactory):
    """Create the standard registry-dispatched, single-writer delta adapter."""

    def create(
        self,
        *,
        reducer: Reducer,
        delta_handler_registry: DeltaHandlerRegistry,
    ) -> DeltaReducer:
        return RegistryDeltaReducer(reducer, delta_handler_registry)


class DefaultCheckpointStateResolverFactory(CheckpointStateResolverFactory):
    """Create the standard state-store-backed checkpoint resolver."""

    def create(self, *, state_store: StateStore) -> CheckpointStateResolver:
        return DeclarativeCheckpointStateResolver(state_store=state_store)


class DefaultResultFinalizerFactory(ResultFinalizerFactory):
    """Create the standard reducer-driven terminal result finalizer."""

    def create(
        self,
        *,
        reducer: Reducer,
        hooks: HookRegistry,
        artifact_closure: ArtifactClosure,
        state_store: StateStore,
    ) -> ResultFinalizer:
        return RuntimeResultFinalizer(
            reducer=reducer,
            hooks=hooks,
            artifact_closure=artifact_closure,
            state_store=state_store,
        )


class DefaultDeclarativeInterpreterFactory(DeclarativeInterpreterFactory):
    """Build the production interpreter with the five runtime closures.

    After the act-subgraph seam cutover (note 2026-09-11),
    ``PlanInterpreterAdapter`` is the sole production interpreter.
    The adapter wraps ``PlanInterpreter`` and stores the runtime
    closures so host-injected strategy closures can reach them.
    """

    def __init__(
        self,
        loop_guard_evaluator: object | None = None,
    ) -> None:
        self._loop_guard_evaluator = loop_guard_evaluator

    def create(
        self,
        *,
        journal: RuntimeJournal,
        effect_gateway: EffectDispatcher,
        reducer: DeltaReducer,
        phase_observer: object,
        lifecycle_publisher: RuntimeLifecyclePublisher,
        phase_executors: object | None = None,
        phase_capabilities: object | None = None,
        node_executors: object | None = None,
        node_executor_runtime_scope: object | None = None,
        graph_observer: object | None = None,
        graph_clock: object | None = None,
    ) -> DeclarativeInterpreter:
        return PlanInterpreterAdapter(
            journal=journal,
            effect_gateway=effect_gateway,
            reducer=reducer,
            phase_observer=phase_observer,
            lifecycle_publisher=lifecycle_publisher,
            loop_guard_evaluator=self._loop_guard_evaluator,
            phase_executors=phase_executors,
            phase_capabilities=phase_capabilities,
            node_executors=node_executors,
            node_executor_runtime_scope=node_executor_runtime_scope,
            graph_observer=graph_observer,
            graph_clock=graph_clock,
        )


class ObservabilityRuntimeJournalFactory(RuntimeJournalFactory):
    """Create one observability-backed journal for each runtime turn."""

    def create(self) -> RuntimeJournal:
        return RuntimeJournalCommitter()


@plugin(
    id="lca-declarative-runtime-seams-provider",
    requires=[
        "loop_guard_evaluator",
    ],
    provides=[
        "checkpoint_state_resolver_factory",
        "declarative_interpreter_factory",
        "delta_reducer_factory",
        "effect_dispatcher_factory",
        "result_finalizer_factory",
        "runtime_journal_factory",
    ],
    implements=[
        CheckpointStateResolverFactory,
        DeclarativeInterpreterFactory,
        DeltaReducerFactory,
        EffectDispatcherFactory,
        ResultFinalizerFactory,
        RuntimeJournalFactory,
    ],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default checkpoint, terminal, Gateway, DeltaReducer, and per-turn "
        "Journal factories for declarative runtime assembly."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("decision.emit",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-declarative-runtime-seams-provider.checked",
                "lca-declarative-runtime-seams-provider.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(
            "checkpoint_state_resolver_factory",
            "decision.emit",
            "declarative_interpreter_factory",
            "delta_reducer_factory",
            "effect_dispatcher_factory",
            "result_finalizer_factory",
            "runtime_journal_factory",
        ),
        emits=(
            "checkpoint_state_resolver_factory.checked",
            "declarative_interpreter_factory.checked",
            "delta_reducer_factory.checked",
            "effect_dispatcher_factory.checked",
            "result_finalizer_factory.checked",
            "runtime_journal_factory.checked",
        ),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register default factory choices as independently replaceable capabilities."""

    del config
    ctx.provide("checkpoint_state_resolver_factory", DefaultCheckpointStateResolverFactory())

    ctx.provide(
        "declarative_interpreter_factory",
        DefaultDeclarativeInterpreterFactory(
            ctx.require("loop_guard_evaluator"),
        ),
    )
    ctx.provide("delta_reducer_factory", RegistryDeltaReducerFactory())
    ctx.provide("effect_dispatcher_factory", RegistryEffectDispatcherFactory())
    ctx.provide("result_finalizer_factory", DefaultResultFinalizerFactory())
    ctx.provide("runtime_journal_factory", ObservabilityRuntimeJournalFactory())


__all__ = [
    "Config",
    "DefaultCheckpointStateResolverFactory",
    "DefaultDeclarativeInterpreterFactory",
    "DefaultResultFinalizerFactory",
    "ObservabilityRuntimeJournalFactory",
    "RegistryDeltaReducerFactory",
    "RegistryEffectDispatcherFactory",
    "setup",
]
