"""Shared primitives used by plan-bound sub-composers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from lca.contracts.atoms.enums import ActionScope, ComponentKind, DecisionGateName
from lca.contracts.capabilities import (
    BRAINS,
    COMPONENT_REGISTRY,
    OBSERVABILITY,
)
from lca.contracts.mechanisms import consume
from lca.contracts.mechanisms.capability import (
    MissingCapabilityError,
    provider_current,
    require_capability,
)
from lca.contracts.protocols import (
    Brain,
    DecisionGate,
    LLMAdapter,
    MemorySystem,
    ObservabilityBackend,
    PerceiveHub,
    SharedMemoryStore,
    StateStore,
)
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.protocols.spec import AgentSpec, LeadSpec, TeamSpec, strategy_key_for_governance
from lca.layer0_infra.observability import BoundObservability, TeamTraceProfile, team_id_for
from lca.layer0_infra.observability.adapters import TelemetryLLMAdapter, TelemetryMemoryAdapter
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import PromptReasoner

if TYPE_CHECKING:
    from lca.contracts.harness.composer import TeamGraph


@dataclass(frozen=True, slots=True)
class AgentCompositionRequest:
    """The complete composition-time input for one plan-bound AgentGraph."""

    spec: AgentSpec
    action_scope: ActionScope = ActionScope.SOLO
    team_channel: AgentTransport | None = None
    decision_gate: DecisionGate | None = None
    shared_store: SharedMemoryStore | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.spec, name)


def require_factory(scope: object, key: str) -> Any:
    return require_capability(scope, key)


def _skill_store_from_scope(scope: object) -> Any:
    """Resolve the active skill store from the plan composition scope."""

    store = provider_current(require_capability(scope, "skills"))
    if store is None:
        raise MissingCapabilityError("skills")
    return store


def _skill_store(scope: object) -> Any:
    return _skill_store_from_scope(scope)


def _render_available_skills(scope: object) -> str:
    """Render installed skill metadata for the model-visible prompt catalog."""

    try:
        packages = _skill_store_from_scope(scope).list_installed()
    except Exception:
        return "（无可用技能；可使用 search_skill 查找）"
    lines = [
        f"- {package.skill_id}: {package.name} — {package.summary} (v{package.version})"
        for package in packages
    ]
    return "\n".join(lines) or "（无可用技能；可使用 search_skill 查找）"


def _format_tools_xml(tools: list[Any] | tuple[Any, ...]) -> str:
    """Render Tool metadata into the prompt's stable XML-like catalog."""

    return "\n".join(
        f'<tool name="{tool.name}">{tool.description or tool.name}</tool>' for tool in tools
    )


def instrument_llm(llm: LLMAdapter) -> LLMAdapter:
    return TelemetryLLMAdapter(llm._inner if isinstance(llm, TelemetryLLMAdapter) else llm)


def resolve_brain(spec: AgentSpec, llm: LLMAdapter, *, scope: object) -> Brain:
    if not isinstance(spec.brain, str):
        return spec.brain
    brains = require_capability(scope, BRAINS.key)
    try:
        factory = brains.resolve(spec.brain)
    except KeyError as exc:
        raise ValueError(f"Unknown brain: {spec.brain!r}. Available: {brains.names()}") from exc
    try:
        installed = _skill_store(scope).list_installed()
    except Exception:
        installed = ()
    skills = "\n".join(f"- {item.skill_id}: {item.name}" for item in installed) or "（无可用技能）"
    tools = (
        "\n".join(
            f'<tool name="{tool.name}">{tool.description or tool.name}</tool>'
            for tool in spec.tools
        )
        or "（无可用工具）"
    )
    return factory(
        consume("llm", llm, PromptReasoner),
        spec.profile,
        tools,
        tools=list(spec.tools),
        available_skills=skills,
    )


def apply_lead_brain(brain: Brain, decision_gate: DecisionGate) -> Brain:
    if not isinstance(brain, ModularBrain):
        raise TypeError(f"lead composition requires ModularBrain (got {type(brain).__name__})")
    return ModularBrain(
        reasoner=brain.reasoner,
        critic=brain.critic,
        skill_router=brain.skill_router,
        decision_gate=decision_gate,
        agent_gates=brain.agent_gates,
    )


def resolve_decision_gate(name: DecisionGateName, *, scope: object) -> DecisionGate | None:
    if name == DecisionGateName.NONE:
        return None
    if name == DecisionGateName.MUST_CONSULT_ALL:
        result = require_capability(scope, "gates").create("must-consult-all")
    else:
        result = require_capability(scope, COMPONENT_REGISTRY.key).require(
            ComponentKind.DECISION_GATE, name
        )()
    if not isinstance(result, DecisionGate):
        raise TypeError(
            f"decision_gate factory produced {type(result).__name__}, expected DecisionGate"
        )
    return result


def resolve_memory(
    choice: str | MemorySystem,
    shared_store: SharedMemoryStore | None,
    memory_service: Any,
) -> MemorySystem:
    if shared_store is not None:
        memory: MemorySystem = memory_service.create(shared_store=shared_store)
    elif not isinstance(choice, str):
        memory = choice
    elif choice in memory_service.providers.names():
        memory = memory_service.providers.get(choice)()
    else:
        raise MissingCapabilityError("memory")
    return TelemetryMemoryAdapter(memory)


def resolve_state_store(choice: str | StateStore, service: Any) -> StateStore:
    if not isinstance(choice, str):
        return choice
    if choice in service.providers.names():
        return cast("StateStore", service.providers.get(choice)())
    raise MissingCapabilityError("state_store")


def fork_transport(parent: Any, extra: AgentTransport | None, scope: object) -> Any:
    child = require_factory(scope, "transport.compose_service")()
    for protocol in parent.list_protocols():
        child.register(parent.resolve(protocol))
    if extra is not None:
        child.register(extra)
    return child


def build_perceive_hub(
    memory: MemorySystem,
    *,
    hub: object,
    scope: object,
    action_scope: ActionScope,
) -> PerceiveHub:
    store = getattr(hub, "_run_store", None) or getattr(scope, "run_store", None)
    store = store or getattr(scope, "_run_store", None) or require_factory(scope, "journal_store")()
    service = require_capability(scope, "perceive")
    team = action_scope in {ActionScope.LEAD, ActionScope.MEMBER}
    members = service.members(team=team)
    skill_store = (
        _skill_store(scope)
        if any(getattr(item, "needs", None) == "skills" for item in members)
        else None
    )
    return cast(
        "PerceiveHub", service.assemble(memory, store=store, skill_store=skill_store, team=team)
    )


def resolve_observability(spec: AgentSpec, scope: object) -> BoundObservability:
    if isinstance(spec.observability, BoundObservability):
        return spec.observability
    if isinstance(spec.observability, str):
        return cast("BoundObservability", require_capability(scope, OBSERVABILITY.key))
    raise TypeError(
        "AgentSpec.observability must resolve to BoundObservability in plan composition"
    )


def resolve_team_observability(spec: TeamSpec, scope: object) -> BoundObservability:
    candidates: list[str | ObservabilityBackend | BoundObservability] = []
    if spec.observability is not None:
        candidates.append(spec.observability)
    candidates.extend(member.observability for member in spec.members)
    if isinstance(spec.governance, LeadSpec):
        candidates.append(spec.governance.agent.observability)
    for candidate in candidates:
        if isinstance(candidate, BoundObservability):
            return candidate
        if isinstance(candidate, str):
            return cast("BoundObservability", require_capability(scope, OBSERVABILITY.key))
    return cast("BoundObservability", require_capability(scope, OBSERVABILITY.key))


def team_trace_profile(spec: TeamSpec, graph: TeamGraph) -> TeamTraceProfile:
    lead = graph.metadata.get("lead")
    strategy_key = strategy_key_for_governance(spec.governance)
    mandate = spec.governance.mandate.value if isinstance(spec.governance, LeadSpec) else None
    return TeamTraceProfile(
        team_id=team_id_for(strategy_key),
        strategy_key=strategy_key,
        mandate=mandate,
        lead_role=lead.role_profile.role if lead is not None else "",
        member_roles=tuple(member.role_profile.role for member in graph.members),
    )


__all__ = [
    "AgentCompositionRequest",
    "_format_tools_xml",
    "_render_available_skills",
    "_skill_store_from_scope",
    "apply_lead_brain",
    "build_perceive_hub",
    "fork_transport",
    "instrument_llm",
    "require_factory",
    "resolve_brain",
    "resolve_decision_gate",
    "resolve_memory",
    "resolve_observability",
    "resolve_state_store",
    "resolve_team_observability",
    "team_trace_profile",
]
