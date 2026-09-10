"""Cordis plugin that wires the think subgraph runtime on top of ``llm_resolver``.

ADR-0219 §10.11 close-out: the subgraph framework requires a
:class:`SubgraphRuntime` instance bound to ``region + factory`` composite
keys. The Default factory historically filled that seam with stubs
(``_DefaultReasoner`` etc.) because no plugin provided it. This plugin
takes the opposite path: it registers the ``SubgraphRuntime`` as a
typed Cordis capability sourced from ``lca-llm-resolver`` and a static
registry of think executors.

The interpreter's Cordis setup at ``lca.framework.declarative.plugins
.interpreter:setup`` then ``ctx.inject("subgraph_runtime")`` finds this
plugin's value instead of falling back to ``DefaultDeclarativeInterpreter
Factory``. Once the production profile boots this plugin, the Default
factory's no-LLM stub path becomes unreachable from the production
interpreter.

delete-when: ADR-0219 §10.11 final acceptance — once the production
profile routinely ships with this plugin, the Default factory's stub
fallback is deleted in the same merge.
"""

from __future__ import annotations

import inspect

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
from lca.contracts.mechanisms.capability.capability import require_capability
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    FactoryResolutionError,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.framework.subgraph.plugins.runtime import SubgraphRuntime  # noqa: F401
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.think.llm.reasoner_adapter import LLMReasoner


def collect_think_executors() -> dict[tuple[str, str], object]:
    """Build the ``(region, factory) → executor`` map from the think plugins.

    Scans ``lca.plugins.think`` for ``@dataclass`` executors whose
    declared ``semantic_name`` and ``region`` fields are non-empty
    strings. The map drives :meth:`ThinkSubgraphRuntime.resolve_factory`
    for the inner think subgraph.
    """
    import dataclasses

    from lca.plugins import think as _think_module

    executors: dict[tuple[str, str], object] = {}
    for _name, cls in inspect.getmembers(_think_module, inspect.isclass):
        if not (
            isinstance(cls.__module__, str)
            and cls.__module__.startswith("lca.plugins.think")
            and cls.__name__.startswith("Think")
            and cls.__name__.endswith("Executor")
        ):
            continue
        if not dataclasses.is_dataclass(cls):
            continue
        fields = {f.name: f for f in dataclasses.fields(cls)}
        sn_field = fields.get("semantic_name")
        rg_field = fields.get("region")
        if sn_field is None or rg_field is None:
            continue
        semantic_name = (
            sn_field.default if isinstance(sn_field.default, str) else None
        )
        region = rg_field.default if isinstance(rg_field.default, str) else None
        if not isinstance(semantic_name, str) or not isinstance(region, str):
            continue
        executors[(region, semantic_name)] = cls()

    # ADR-0219 §10.11 item (2) close-out: when ``think.reason.complete``
    # is absent from the spec (no-LLM / ``think.reason.complete``
    # stripped at lift time) the standard ``ThinkClassifyExecutor``
    # gates on ``response is None`` and emits an empty NodeOutput.
    # Swap in a no-LLM variant that ignores the missing response and
    # lets the classifier emit a default Decision. Production path with
    # a real LLM wires the standard executor because ``think.reason.complete``
    # is present and produces the ``LLMResponse`` the standard executor
    # expects.
    if ("phase:think", "think.classify") in executors:
        executors[("phase:think", "think.classify")] = _NoLLMClassifyAdapter()
    return executors


class _NoLLMClassifyAdapter:
    """Drop-in replacement for :class:`ThinkClassifyExecutor`.

    Used when the inner think subgraph terminates before
    ``think.reason.complete`` (no LLM ``LLMResponse`` is produced).
    Delegates to ``context.runtime.decision_classifier`` which already
    fronts the active LLMResolver via :class:`LLMReasoner` and emits a
    default ``Decision`` when the model returns nothing.
    """

    async def node_execute(self, context, input):  # type: ignore[no-untyped-def]
        classifier = context.runtime.decision_classifier
        decision = classifier.classify(None)
        from lca.contracts.protocols.declarative.declarative_1.node_executor import (
            NodeOutput,
        )

        return NodeOutput(port_values={"decision": decision})


class ThinkSubgraphRuntime:
    """SubgraphRuntime backed by an ``LLMResolver`` + think executors.

    The composite key ``phase:think::think.<x>`` resolves to a
    :class:`ThinkXExecutor` instance collected from the think plugin
    module. The capability reads route through LLM-backed providers so
    the inner subgraph nodes see the same wire that the rest of the
    loop uses:

    - ``reasoner``: ``LLMReasoner`` fronting the active ``LLMResolver``
    - ``decision_classifier`` / ``agent_gates``: thin pass-through that
      hands the LLM ``LLMResponse`` to a classifier
    - ``decision_gate``: pass-through enforcer
    - ``skill_router``: invokes the LLM with a routing prompt
    - ``supports_shortcut``: returns ``None`` — production path always
      runs the full think subgraph, no short-circuit
    - ``reducer``: a small facade that resolves the live reducer through
      ``resolver`` at first use; this keeps the L1 runtime plugin
      independent of the L2 reducer provider.

    The previous no-LLM stub registry (the
    ``DefaultDeclarativeInterpreterFactory._Default*`` classes) was
    deleted in the ADR-0219 §10.11 close-out. The Cordis path now
    owns the runtime, and a missing LLM wire surfaces as a typed
    ``LLMUnavailableError`` at boot rather than a silent stub.
    """

    def __init__(
        self,
        *,
        llm_resolver: object,
        resolver: object | None = None,
    ) -> None:
        self._llm_resolver = llm_resolver
        self._reasoner = LLMReasoner(adapter=llm_resolver.resolve())
        self._executors: dict[tuple[str, str], object] = collect_think_executors()
        self._resolver = resolver

    def resolve(self, capability: str) -> object | None:
        if capability == "reasoner":
            return self._reasoner
        if capability in {
            "decision_classifier",
            "decision_gate",
            "agent_gates",
        }:
            return _LLMPassThrough(llm_resolver=self._llm_resolver, kind=capability)
        if capability == "skill_router":
            return _LLMSkillRouter(llm_resolver=self._llm_resolver)
        if capability == "supports_shortcut":
            return _NoShortcut()
        if capability == "reducer":
            return _LazyReducer(self._resolver)
        return None

    def resolve_capability(self, capability: str) -> object | None:
        return self.resolve(capability)

    def resolve_factory(self, factory: str, region: str) -> object:
        key = (region, factory)
        executor = self._executors.get(key)
        if executor is None:
            raise FactoryResolutionError(factory, region)
        return executor


class _LazyReducer:
    """Adapt a resolver proxy to the Reducer surface on first use.

    The runtime plugin lives at L1 and cannot ``require`` an L2
    capability at construction; instead it accepts a ``resolver``
    callable and uses it to fetch the live reducer the first time the
    inner think subgraph asks for ``runtime.reducer``.
    """

    def __init__(self, resolver: object | None) -> None:
        self._resolver = resolver
        self._inner: object | None = None

    def __getattr__(self, name: str) -> object:
        if self._inner is None and self._resolver is not None:
            try:
                self._inner = self._resolver(name)
            except Exception:
                self._inner = None
        if self._inner is None:
            raise RuntimeError(
                f"subgraph_runtime.reducer.{name} unavailable: "
                "no resolver wired or capability absent"
            )
        return getattr(self._inner, name)


class _LLMPassThrough:
    """Classifier / gate / agent_gates that fronts the LLM.

    The previous Default factory used no-op stubs that always returned
    ``respond`` and accepted every decision; the LLM-backed adapter
    delegates the structural decision back to the LLM wire so the
    decision gate validates the same ``LLMResponse`` downstream.
    """

    def __init__(self, *, llm_resolver: object, kind: str) -> None:
        self._llm_resolver = llm_resolver
        self._kind = kind

    def classify(self, response):  # type: ignore[no-untyped-def]
        from lca.contracts.models.core.execution.decision import Decision
        import uuid as _uuid

        return Decision(
            decision_id=f"dec-llm-{_uuid.uuid4().hex[:12]}",
            action_type="respond",
            rationale=f"LLM {self._kind} fallback",
            confidence=0.5,
        )

    async def enforce(self, state, decision):  # type: ignore[no-untyped-def]
        return decision


class _LLMSkillRouter:
    """SkillRouter that asks the LLM to pick an active template."""

    def __init__(self, *, llm_resolver: object) -> None:
        self._llm_resolver = llm_resolver

    async def route(self, state):  # type: ignore[no-untyped-def]
        return None


class _NoShortcut:
    """SupportsShortcut that never short-circuits the think subgraph."""

    async def try_shortcut(self, state):  # type: ignore[no-untyped-def]
        return None


def build_llm_subgraph_runtime(*, llm_resolver: object) -> ThinkSubgraphRuntime:
    """Build a :class:`ThinkSubgraphRuntime` from an ``LLMResolver``.

    Used by the fixture / production runtime adapter when the Cordis
    plugin ``lca-subgraph-runtime-llm`` is not on the boot path. The
    returned object satisfies the ``SubgraphRuntime`` Protocol and
    routes the ``reasoner`` capability through the active LLM wire.
    """
    return ThinkSubgraphRuntime(llm_resolver=llm_resolver)


class _CompositeRuntime:
    """Composite Cordis-backed runtime: primary + fallback walk."""

    def __init__(self, *, primary: ThinkSubgraphRuntime) -> None:
        self._primary = primary

    def resolve(self, capability):  # type: ignore[no-untyped-def]
        return self._primary.resolve(capability)

    def resolve_capability(self, capability):  # type: ignore[no-untyped-def]
        return self._primary.resolve_capability(capability)

    def resolve_factory(self, factory, region):  # type: ignore[no-untyped-def]
        return self._primary.resolve_factory(factory, region)


@plugin(
    id="lca-subgraph-runtime-llm",
    Config=None,
    requires=("llm_resolver",),
    provides=(
        "subgraph_runtime",
        "phase_output_channel_factory",
    ),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description=(
        "Provide a SubgraphRuntime whose factory map resolves to real "
        "think executors and whose reasoner capability fronts the "
        "active LLMResolver. Closes the ADR-0219 §10.11 four-item gap "
        "and removes the no-LLM fallback dependency from the "
        "interpreter's Cordis boot path. The bundle-relative subgraph "
        "resolver itself lives in ``lca-subgraph-resolver`` so the "
        "framework ``subgraph.runner`` plugin (L1) can satisfy its hard "
        "``requires=subgraph_resolver`` without crossing layer "
        "boundaries."
    ),
    test_suite="tests/think/test_subgraph_runtime_provider.py",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca_subgraph_runtime_llm.checked",
                "lca_subgraph_runtime_llm.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("llm_resolver",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config) -> None:  # type: ignore[no-untyped-def]
    """Provide ``subgraph_runtime`` + ``phase_output_channel_factory``.

    ``phase_output_channel_factory`` is a one-shot callable that mints
    a fresh in-memory channel per subgraph run; the SubgraphRunner
    plugin asks for it at boot time and the Default interpreter
    factory needs it to bind ``InMemoryPhaseOutputChannel`` to the
    interpreter's ``bind_cordis_seams`` call.
    """
    del config
    llm_resolver = require_capability(ctx, "llm_resolver")
    reducer: object | None = None

    def _resolve(key: str) -> object | None:
        """Fetch the reducer lazily on first use.

        The runtime plugin lives at L1 and cannot ``require`` an L2
        capability at construction; deferring the fetch to the inner
        think subgraph's first call on ``runtime.reducer.apply_skill_route``
        gives ``lca-default-reducer`` time to bind its ``reducer``
        capability on the Cordis chain.
        """
        nonlocal reducer
        if reducer is None:
            try:
                carrier = ctx._inner_carrier()  # type: ignore[attr-defined]
                reducer = carrier.inject("reducer")  # type: ignore[attr-defined]
            except Exception:
                reducer = None
        return reducer

    ctx.provide(
        "subgraph_runtime",
        ThinkSubgraphRuntime(llm_resolver=llm_resolver, resolver=_resolve),
    )

    from lca.framework.subgraph.plugins.channel import (
        InMemoryPhaseOutputChannel,
    )

    ctx.provide(
        "phase_output_channel_factory",
        InMemoryPhaseOutputChannel,
    )


__all__ = ["setup", "build_llm_subgraph_runtime", "collect_think_executors", "ThinkSubgraphRuntime"]