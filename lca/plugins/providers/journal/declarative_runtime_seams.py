"""Default factories for declaratively selected runtime execution seams.

These factories preserve the existing registry-backed behavior while moving its
concrete construction out of ``DeclarativeRuntimeBindings``.  A profile can
replace any factory capability without changing the runtime kernel.
"""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.mechanisms import HookRegistry
from lca.contracts.protocols.act.effect_handler import EffectCapabilities, EffectHandlerRegistry
from lca.contracts.protocols.declarative.declarative_phase_graph import DeltaReducer, EffectGateway
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.journal.artifact_closure import ArtifactClosure
from lca.contracts.protocols.journal.idempotency import IdempotencyStore
from lca.contracts.protocols.runtime.infra import StateStore
from lca.contracts.protocols.runtime.runtime_composition import (
    CheckpointStateResolver,
    CheckpointStateResolverFactory,
    DeclarativeInterpreter,
    DeclarativeInterpreterFactory,
    DeltaReducerFactory,
    EffectGatewayFactory,
    ResultFinalizer,
    ResultFinalizerFactory,
    RuntimeJournal,
    RuntimeJournalFactory,
)
from lca.contracts.protocols.runtime.runtime_lifecycle import RuntimeLifecyclePublisher
from lca.contracts.protocols.state.delta_handler import DeltaHandlerRegistry
from lca.contracts.protocols.state.reducer import Reducer
from lca.harness.declarative import GenericPlanInterpreter
from lca.harness.declarative.execute.dispatch import RegistryDeltaReducer, RegistryEffectGateway
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.runtime.checkpoint_resolution import DeclarativeCheckpointStateResolver
from lca.runtime.result_finalizer import RuntimeResultFinalizer
from lca.runtime.runtime_journal import RuntimeJournalCommitter


class Config(BaseModel):
    """Default declarative runtime-factory configuration."""

    model_config = {"extra": "forbid"}


class RegistryEffectGatewayFactory(EffectGatewayFactory):
    """Create the standard policy and idempotency governed effect gateway."""

    def create(
        self,
        *,
        capabilities: EffectCapabilities,
        effect_handler_registry: EffectHandlerRegistry,
        idempotency_store: IdempotencyStore,
    ) -> EffectGateway:
        return RegistryEffectGateway(
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
    """Build the standard interpreter with its local traversal policy."""

    def __init__(self, loop_guard_evaluator: object | None = None) -> None:
        self._loop_guard_evaluator = loop_guard_evaluator

    def create(
        self,
        *,
        journal: RuntimeJournal,
        effect_gateway: EffectGateway,
        reducer: DeltaReducer,
        phase_observer: object,
        lifecycle_publisher: RuntimeLifecyclePublisher,
    ) -> DeclarativeInterpreter:
        return cast(
            "DeclarativeInterpreter",
            GenericPlanInterpreter(
                journal=journal,
                effect_gateway=effect_gateway,
                reducer=reducer,
                phase_observer=phase_observer,
                loop_guard_evaluator=self._loop_guard_evaluator,
                lifecycle_publisher=lifecycle_publisher,
            ),
        )


class ObservabilityRuntimeJournalFactory(RuntimeJournalFactory):
    """Create one observability-backed journal for each runtime turn."""

    def create(self) -> RuntimeJournal:
        return RuntimeJournalCommitter()


@plugin(
    id="lca-declarative-runtime-seams-provider",
    requires=["loop_guard_evaluator"],
    provides=[
        "checkpoint_state_resolver_factory",
        "declarative_interpreter_factory",
        "delta_reducer_factory",
        "effect_gateway_factory",
        "result_finalizer_factory",
        "runtime_journal_factory",
    ],
    implements=[
        CheckpointStateResolverFactory,
        DeclarativeInterpreterFactory,
        DeltaReducerFactory,
        EffectGatewayFactory,
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
            "effect_gateway_factory",
            "result_finalizer_factory",
            "runtime_journal_factory",
        ),
        emits=(
            "checkpoint_state_resolver_factory.checked",
            "declarative_interpreter_factory.checked",
            "delta_reducer_factory.checked",
            "effect_gateway_factory.checked",
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
        DefaultDeclarativeInterpreterFactory(ctx.require("loop_guard_evaluator")),
    )
    ctx.provide("delta_reducer_factory", RegistryDeltaReducerFactory())
    ctx.provide("effect_gateway_factory", RegistryEffectGatewayFactory())
    ctx.provide("result_finalizer_factory", DefaultResultFinalizerFactory())
    ctx.provide("runtime_journal_factory", ObservabilityRuntimeJournalFactory())


__all__ = [
    "Config",
    "DefaultCheckpointStateResolverFactory",
    "DefaultDeclarativeInterpreterFactory",
    "DefaultResultFinalizerFactory",
    "ObservabilityRuntimeJournalFactory",
    "RegistryDeltaReducerFactory",
    "RegistryEffectGatewayFactory",
    "setup",
]
