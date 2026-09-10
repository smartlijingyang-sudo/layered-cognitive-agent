"""Cordis plugin that wires the think subgraph runtime on top of ``llm_resolver``.

Provides ``subgraph_runtime`` and ``phase_output_channel_factory`` so the
framework ``subgraph.runner`` and the declarative interpreter's
``bind_cordis_seams`` find what they need at boot.

The runtime is backed by ``PromptReasoner`` (the standard Reasoner in
``lca.cognition.brain.reasoner.reasoner``) wrapping the active
``LLMResolver``. ``PromptReasoner`` already implements the three methods
the inner think subgraph reads via ``context.runtime.reasoner``:
``build_turn_plan`` (think.reason.plan), ``render_turn`` (think.reason.render)
and ``complete_turn`` (think.reason.complete). This is the same three-step
shape that ``run_reasoner_generate_thoughts_with_spine_facts`` decomposes
into — the subgraph path is the graph-encoded equivalent of the
single-phase spine call.

No stub registry, no fallback. If the LLMResolver is absent the
``lca-llm-resolver`` plugin's contract fails at boot.
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


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
        semantic_name = sn_field.default if isinstance(sn_field.default, str) else None
        region = rg_field.default if isinstance(rg_field.default, str) else None
        if not isinstance(semantic_name, str) or not isinstance(region, str):
            continue
        executors[(region, semantic_name)] = cls()
    return executors


class ThinkSubgraphRuntime:
    """SubgraphRuntime backed by ``PromptReasoner`` + think executors.

    ``reasoner`` capability is a ``PromptReasoner`` constructed with the
    active ``LLMResolver`` — same wire the rest of the loop uses. The
    three subgraph nodes (plan/render/complete) call the same
    ``build_turn_plan`` / ``render_turn`` / ``complete_turn`` methods
    that the single-phase path called sequentially.

    Other capabilities return simple pass-through adapters so the
    surrounding subgraph machinery has something to read.
    """

    def __init__(self, *, llm_resolver: object) -> None:
        self._llm_resolver = llm_resolver
        self._reasoner = self._build_reasoner()
        self._executors: dict[tuple[str, str], object] = collect_think_executors()

    def _build_reasoner(self):
        """Build a ``PromptReasoner`` from the active LLMResolver.

        ``PromptReasoner`` accepts a pre-constructed ``LLMAdapter`` (or
        uses its default); we resolve the adapter here so the same wire
        serves both the outer brain and the inner subgraph.
        """
        from lca.cognition.brain.reasoner.reasoner import PromptReasoner
        from lca.contracts.models.team.role.team import (
            RoleProfile,
            ToolPermissionManifest,
        )

        adapter = self._llm_resolver.resolve()
        role_profile = RoleProfile(
            role="assistant",
            goal="answer user questions",
            backstory="LCA inner think subgraph reasoner",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        return PromptReasoner(llm=adapter, role_profile=role_profile)

    def resolve(self, capability: str) -> object | None:
        if capability == "reasoner":
            return self._reasoner
        if capability == "decision_classifier":
            from lca.plugins.gate.decision_classifier_provider import DefaultDecisionClassifier

            return DefaultDecisionClassifier()
        if capability in {"decision_gate", "agent_gates"}:
            return _NoGateEnforce()
        if capability == "skill_router":
            return _NoSkillRouter()
        if capability == "supports_shortcut":
            return _NoShortcut()
        if capability == "reducer":
            from lca.plugins.loop.reducer.plugin import DefaultReducer

            return DefaultReducer()
        return None

    def resolve_capability(self, capability: str) -> object | None:
        return self.resolve(capability)

    def resolve_factory(self, factory: str, region: str) -> object:
        executor = self._executors.get((region, factory))
        if executor is None:
            raise FactoryResolutionError(factory, region)
        return executor


class _NoGateEnforce:
    """DecisionGate surface that returns the candidate decision unchanged.

    Used for ``decision_gate`` and ``agent_gates`` capability keys inside the
    inner think subgraph. Those slots are ``DecisionGate | None`` and are
    normally injected from the profile (see ``ChainedDecisionGateAssembler``);
    when no profile binding is present the subgraph passes the candidate
    decision through rather than fabricating one.
    """

    async def enforce(self, state, decision):  # type: ignore[no-untyped-def]
        return decision


class _NoSkillRouter:
    """SkillRouter that never routes; outer pipeline handles skill activation."""

    async def route(self, state):  # type: ignore[no-untyped-def]
        return None


class _NoShortcut:
    """SupportsShortcut that never short-circuits the think subgraph."""

    async def try_shortcut(self, state):  # type: ignore[no-untyped-def]
        return None


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
        "Provide a SubgraphRuntime whose factory map resolves to the "
        "think executors and whose reasoner capability is a "
        "PromptReasoner wrapping the active LLMResolver. Closes the "
        "interpreter bind_cordis_seams gap without inventing a "
        "reasoner_adapter layer — the subgraph three-node plan / "
        "render / complete calls the same PromptReasoner methods the "
        "single-phase path used."
    ),
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
    del config
    llm_resolver = require_capability(ctx, "llm_resolver")
    ctx.provide(
        "subgraph_runtime",
        ThinkSubgraphRuntime(llm_resolver=llm_resolver),
    )

    from lca.framework.subgraph.plugins.channel import (
        InMemoryPhaseOutputChannel,
    )

    ctx.provide(
        "phase_output_channel_factory",
        InMemoryPhaseOutputChannel,
    )


__all__ = ["ThinkSubgraphRuntime", "collect_think_executors", "setup"]
