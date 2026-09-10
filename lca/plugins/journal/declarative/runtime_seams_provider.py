"""Default factories for declaratively selected runtime execution seams.

These factories preserve the existing registry-backed behavior while moving its
concrete construction out of ``DeclarativeRuntimeBindings``.  A profile can
replace any factory capability without changing the runtime kernel.
"""

from __future__ import annotations

import dataclasses
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

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
from lca.contracts.protocols.gate.loop_guard import LoopGuardEvaluator
from lca.contracts.protocols.journal.artifact.closure import ArtifactClosure
from lca.contracts.protocols.journal.idempotency.idempotency import IdempotencyStore
from lca.contracts.protocols.journal.phase.observation import PhaseObserver
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
from lca.framework.declarative.plugins.interpreter import GenericPlanInterpreter
from lca.harness.declarative.compile.subgraph_resolver import default_subgraph_resolver
from lca.harness.declarative.execute.dispatch import RegistryDeltaReducer, RegistryEffectDispatcher
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.runtime.loop.runtime_journal import RuntimeJournalCommitter
from lca.runtime.projection.result_finalizer import RuntimeResultFinalizer
from lca.runtime.support.checkpoint_resolution import DeclarativeCheckpointStateResolver

_log = logging.getLogger(__name__)


def session_append_observer() -> Callable[[str, dict[str, Any]], Awaitable[None]]:
    """Build an observer that funnels ``phase_graph.node.{start,end}`` into Session.append.

    ADR-0219 §10.11 item (4): single funnel between the inner driver
    observer port and the durable journal. The closure imports
    :mod:`lca.session.append` lazily to avoid the runtime-seams
    import cycle (the session module imports harness which imports
    this module).

    Returns:
        An async callable ``(event, payload) -> None`` suitable for
        ``SubgraphRunner(observers=(session_append_observer(),))``.
    """
    from lca.session.append import Session

    async def _observer(event: str, payload: dict[str, Any]) -> None:
        Session.append(event, payload)

    return _observer


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
    """Build the standard interpreter with its local traversal policy.

    ADR-0219 §10.5 reject: the v1 ``GraphAssembler + inner _drive`` legacy
    path is deleted. ``SubgraphRunner`` (Cordis-injected) is the single
    seam for subgraph recursion. The factory only owns
    ``subgraph_resolver`` (passed to the runner); ``executable_factory``
    and ``scope`` are gone.
    """

    def __init__(
        self,
        loop_guard_evaluator: object | None = None,
        *,
        subgraph_resolver: object | None = None,
        subgraph_runtime: object | None = None,
        subgraph_runner: object | None = None,
        channel_factory: Callable[[], object] | None = None,
    ) -> None:
        self._loop_guard_evaluator = loop_guard_evaluator
        self._subgraph_resolver = subgraph_resolver or default_subgraph_resolver()
        self._subgraph_runtime = subgraph_runtime
        self._subgraph_runner = subgraph_runner
        self._channel_factory = channel_factory

    def create(
        self,
        *,
        journal: RuntimeJournal,
        effect_gateway: EffectDispatcher,
        reducer: DeltaReducer,
        phase_observer: object,
        lifecycle_publisher: RuntimeLifecyclePublisher,
    ) -> DeclarativeInterpreter:
        # ADR-0219 §10.11: the Default factory no longer ships a stub
        # Reasoner / Classifier / Gate. The interpreter needs a real
        # ``SubgraphRuntime`` whose ``reasoner`` capability fronts the
        # active ``LLMResolver`` (lca-llm-resolver). When the Cordis
        # boot did not provide ``subgraph_runtime`` (Cordis path
        # unreachable, no Cordis ``subgraph_runner`` plugin in the
        # bundle set) the factory raises fail-loud rather than
        # silently re-introducing the no-LLM shortcut. The CLI↔HTTP
        # parity seam at ``composer/runtime/fixture/runtime_adapter``
        # constructs the same factory; profiles that genuinely want
        # an in-process runtime must include ``framework.subgraph``
        # plugins in their bundle set.
        interpreter = cast(
            "DeclarativeInterpreter",
            GenericPlanInterpreter(
                journal=journal,
                effect_gateway=effect_gateway,
                reducer=reducer,
                phase_observer=cast("PhaseObserver | None", phase_observer),
                loop_guard_evaluator=cast("LoopGuardEvaluator | None", self._loop_guard_evaluator),
                lifecycle_publisher=lifecycle_publisher,
            ),
        )
        bind_seams = getattr(interpreter, "bind_cordis_seams", None)
        if not callable(bind_seams):
            return interpreter

        # ADR-0219 §10.11: the think subgraph runtime must be provided
        # by a Cordis plugin (e.g. ``lca-subgraph-runtime-llm``). The
        # Default factory's earlier stub registry was deleted; the
        # requirement is now explicit so operators cannot accidentally
        # ship a run without an LLM wire. ``composer/runtime/fixture
        # /runtime_adapter`` provides the three capabilities at
        # construction time; missing values surface as a typed
        # :exc:`LLMUnavailableError` rather than a silent stub.
        if (
            self._subgraph_runtime is None
            or self._subgraph_runner is None
            or self._channel_factory is None
        ):
            from lca.infrastructure.llm.openai_client import (
                LLMUnavailableError,
            )

            raise LLMUnavailableError(
                "Default factory now requires an LLM-backed subgraph "
                "runtime: provide ``subgraph_runtime``, "
                "``subgraph_runner``, and ``channel_factory`` at "
                "construction. The previous stub registry was "
                "deleted in the ADR-0219 §10.11 close-out; use "
                "``lca-subgraph-runtime-llm`` plus the framework "
                "subgraph.runner plugin in the bundle set."
            )
        bind_seams(
            subgraph_runner=self._subgraph_runner,
            subgraph_runtime=self._subgraph_runtime,
            channel_factory=self._channel_factory,
        )
        return interpreter


class ObservabilityRuntimeJournalFactory(RuntimeJournalFactory):
    """Create one observability-backed journal for each runtime turn."""

    def create(self) -> RuntimeJournal:
        return RuntimeJournalCommitter()


@plugin(
    id="lca-declarative-runtime-seams-provider",
    requires=[
        "loop_guard_evaluator",
        "subgraph_runtime",
        "subgraph_runner",
        "phase_output_channel_factory",
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
    # ADR-0219 §10.11: wire the LLM-backed subgraph runtime at the
    # Cordis seam so the interpreter factory receives the typed
    # ``subgraph_runtime``, ``subgraph_runner``, and
    # ``channel_factory`` it now requires. ``lca-subgraph-runtime-llm``
    # provides ``subgraph_runtime``; the framework ``subgraph.runner``
    # Cordis plugin provides ``subgraph_runner`` and
    # ``phase_output_channel_factory``. When any of these are absent
    # (no LLM wire on the boot path) the factory raises
    # ``LLMUnavailableError`` fail-loud rather than silently
    # substituting a stub Reasoner.
    if hasattr(ctx, "require"):
        try:
            subgraph_runtime = ctx.require("subgraph_runtime")
        except Exception:
            subgraph_runtime = None
        try:
            subgraph_runner = ctx.require("subgraph_runner")
        except Exception:
            subgraph_runner = None
        try:
            channel_factory = ctx.require("phase_output_channel_factory")
        except Exception:
            channel_factory = None
    else:
        subgraph_runtime = subgraph_runner = channel_factory = None
    interpreter_factory = DefaultDeclarativeInterpreterFactory(
        ctx.require("loop_guard_evaluator"),
        subgraph_runtime=subgraph_runtime,
        subgraph_runner=subgraph_runner,
        channel_factory=channel_factory,
    )
    ctx.provide("declarative_interpreter_factory", interpreter_factory)
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
