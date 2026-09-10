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
    ) -> None:
        self._loop_guard_evaluator = loop_guard_evaluator
        self._subgraph_resolver = subgraph_resolver or default_subgraph_resolver()

    def create(
        self,
        *,
        journal: RuntimeJournal,
        effect_gateway: EffectDispatcher,
        reducer: DeltaReducer,
        phase_observer: object,
        lifecycle_publisher: RuntimeLifecyclePublisher,
    ) -> DeclarativeInterpreter:
        # ADR-0219 §10.11 item (2): one-line operator signal that the
        # no-LLM fallback path is engaged. Fires once per create()
        # call so operators can see the difference between the real
        # Reasoner path and the default factory's shortcut.
        _log.info("no-LLM fallback active — think.reason.complete stripped")
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
        # Assembly root:bind_cordis_seams with the think subgraph defaults.
        # 收集 6 个 think plugin dataclass 实例 → (factory, region) registry,
        # 再用 framework 的 SubgraphRunner + InMemoryPhaseOutputChannel。
        # 这条路径在 Cordis boot 不可用的环境(Default factory 不持 ctx)
        # 中提供唯一能跑的 fallback;Cordis-bootstrapped 流程在 runtime_bindings
        # 里覆盖(同名 seam 可重复 bind,后到的赢)。
        bind_seams = getattr(interpreter, "bind_cordis_seams", None)
        if callable(bind_seams):
            from lca.framework.subgraph.plugins.channel import InMemoryPhaseOutputChannel
            from lca.framework.subgraph.plugins.runner import SubgraphRunner
            from lca.plugins import think as _think_module

            registry: dict[tuple[str, str], object] = {}
            for _name, cls in inspect.getmembers(_think_module, inspect.isclass):
                if not (
                    isinstance(cls.__module__, str)
                    and cls.__module__.startswith("lca.plugins.think")
                    and cls.__name__.startswith("Think")
                    and cls.__name__.endswith("Executor")
                ):
                    continue
                # slots dataclass: `getattr(cls, "semantic_name")` returns a
                # member descriptor (not the default string), so reading class
                # attributes fails. Read declared dataclass fields instead.
                if not dataclasses.is_dataclass(cls):
                    continue
                field_map = {f.name: f for f in dataclasses.fields(cls)}
                sn_field = field_map.get("semantic_name")
                rg_field = field_map.get("region")
                if sn_field is None or rg_field is None:
                    continue
                semantic_name = sn_field.default if isinstance(sn_field.default, str) else None
                region = rg_field.default if isinstance(rg_field.default, str) else None
                if not isinstance(semantic_name, str) or not isinstance(region, str):
                    continue
                registry[(region, semantic_name)] = cls()

            from lca.plugins.think.reason.complete import ThinkReasonCompleteExecutor
            registry[("phase:think", "think.reason")] = ThinkReasonCompleteExecutor()

            # Default capability providers (no-cordis fallback):
            # 让 think subgraph 真的跑通完整 5 步 → emit 一个默认 decision。
            # 真实 capability plugin (lca/plugins/runtime_provider/*.py) 会在后续
            # PR 替换;此处先确保 think subgraph 不被空 capability 卡住。

            from lca.contracts.models.core.conversation.llm import LLMResponse
            from lca.contracts.models.core.execution.decision import Decision

            class _DefaultReasoner:
                """Fake Reasoner:返回空 LLMResponse 让 classify 走默认 fallback。"""
                async def generate_thoughts(self, state):
                    return LLMResponse()

            class _DefaultDecisionClassifier:
                """Fake Classifier:空 LLMResponse → emit 默认 respond decision。"""
                def classify(self, response):
                    return Decision(
                        action_type="respond", rationale="default", confidence=1.0,
                    )

            class _DefaultDecisionGate:
                """Fake Gate:passthrough。"""
                async def enforce(self, state, decision):
                    return decision

            class _DefaultSkillRouter:
                """Fake Router:返回空路由。"""
                async def route(self, state):
                    return ""

            class _DefaultSupportsShortcut:
                """Fake Shortcut:没有快速路径。"""
                async def try_shortcut(self, state):
                    return None

            _CAPS = {
                "reasoner": _DefaultReasoner(),
                "decision_classifier": _DefaultDecisionClassifier(),
                "decision_gate": _DefaultDecisionGate(),
                "skill_router": _DefaultSkillRouter(),
                "supports_shortcut": _DefaultSupportsShortcut(),
                "agent_gates": _DefaultDecisionGate(),
            }

            class _DefaultSubgraphRuntime:
                """Default factory 内置的 SubgraphRuntime fallback(无 cordis)。

                提供三种 seam:
                - resolve_factory:(factory, region) → NodeExecutor 解析
                - resolve_capability:(capability_key) → capability 实例,给节点 executor 用
                - resolve:(通用 key → obj) 兼容 SubgraphRuntime Protocol
                """
                def resolve(self, capability):
                    return _CAPS.get(capability)
                def resolve_capability(self, capability):
                    return _CAPS.get(capability)
                def resolve_factory(self, factory, region):
                    return registry.get((region, factory))

            bind_seams(
                subgraph_runner=SubgraphRunner(
                    resolver=self._subgraph_resolver,
                    runtime=_DefaultSubgraphRuntime(),
                    # ADR-0219 §10.11 item (4): wire Session.append into
                    # the inner driver observer port. Single funnel;
                    # no parallel event bus.
                    observers=(session_append_observer(),),
                    channel_factory=InMemoryPhaseOutputChannel,
                    # ADR-0219 §10.11 item (2): the Default factory's
                    # no-LLM fallback strips think.reason.complete at
                    # lift time so the inner graph terminates at render.
                    no_llm_mode=True,
                ),
                subgraph_runtime=_DefaultSubgraphRuntime(),
                channel_factory=InMemoryPhaseOutputChannel,
            )
        return interpreter


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
    interpreter_factory = DefaultDeclarativeInterpreterFactory(
        ctx.require("loop_guard_evaluator"),
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
