"""L4 spawn — close AgentSpec / TeamSpec into live object graphs.

ADR-0056 / ADR-0062 §5: bind per-agent spec from a booted capability scope
only. No concrete service fallbacks. No ``Registries`` / ``defaults.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from cordis import Context

from lca.contracts.atoms.enums import (
    ActionScope,
    ComponentKind,
    DecisionGateName,
    MemoryLayer,
)
from lca.contracts.capabilities import (
    BODIES,
    BRAINS,
    COMPONENT_REGISTRY,
    HOOKS,
    STOP_RULES,
    STRATEGIES,
)
from lca.contracts.mechanisms import consume
from lca.contracts.mechanisms.capability import (
    CapabilityKey,
    MissingCapabilityError,
    provider_current,
    require_capability,
)
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.team_coordination import (
    Coordination,
    LeadMandate,
    gate_name_for_mandate,
)
from lca.contracts.protocols import (
    AgentUnit,
    Brain,
    BudgetPolicy,
    DecisionGate,
    LLMAdapter,
    MemorySystem,
    ObservabilityBackend,
    PerceiveHub,
    SharedMemoryStore,
    StateStore,
    TeamAssembly,
    TeamStage,
    TeamUnit,
)
from lca.contracts.protocols.infra import AgentTransport, Tool
from lca.contracts.protocols.spec import (
    DEFAULT_DELEGATE_MAX_ATTEMPTS,
    OBSERVABILITY_CHOICE_CONSOLE,
    AgentSpec,
    Governance,
    LeadSpec,
    TeamSpec,
    strategy_key_for_governance,
)
from lca.harness.middleware import InMemoryMiddlewareRegistry
from lca.layer0_infra.observability import (
    ObservabilityHub,
    TeamTraceProfile,
    create_observability,
    team_id_for,
)
from lca.layer0_infra.observability.adapters import TelemetryLLMAdapter, TelemetryMemoryAdapter
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import PromptReasoner
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer3_agent.member_invoke import TransportMemberInvoker
from lca.layer3_agent.team_handle import TeamHandle
from lca.layer4_app.policies import LEAD_BUDGET_POLICY_KEY
from lca.layer4_app.runtime_factory import RuntimeDeps, build_cognitive_runtime
from lca.layer4_app.team_wiring import (
    build_default_transport_registry,
    build_team_transport,
)

__all__ = [
    "build_default_transport_registry",
    "build_perceive_hub",
    "build_team_transport",
    "promote_lead",
    "spawn_agent",
    "spawn_lead",
    "spawn_member",
    "spawn_team",
]

T = TypeVar("T")
_NEEDS_SKILLS = "skills"


def _ensure_scope(scope: Context | None) -> Any:
    if scope is not None:
        if not callable(getattr(scope, "inject", None)):
            raise TypeError("spawn scope must be a booted cordis Context with inject()")
        return scope
    from lca.layer4_app.api import get_or_create_default_ctx

    return get_or_create_default_ctx()


def _scope_is_team(scope: object | None) -> bool:
    if scope is None:
        return False
    value = getattr(scope, "value", None)
    if value is not None:
        return str(value).lower() in {"member", "lead", "team"}
    marker = getattr(scope, "team_scope", None) or getattr(scope, "_team_scope", None)
    if marker is None:
        return False
    return str(marker).lower() in {"lead", "member", "team"}


def _run_store_from_scope(scope: object | None) -> Any | None:
    if scope is None:
        return None
    return getattr(scope, "run_store", None) or getattr(scope, "_run_store", None)


def _require_factory(scope: object, key: str) -> Any:
    return require_capability(scope, key)


def _skill_store_from_scope(scope: object) -> Any:
    store = provider_current(require_capability(scope, "skills"))
    if store is None:
        raise MissingCapabilityError("skills")
    return store


def _resolve_component(
    reg: Any,
    category: str,
    value: object,
    expected_type: type[T],
) -> T:
    result = reg.require(category, value)() if isinstance(value, str) else value
    if not isinstance(result, expected_type):
        raise TypeError(
            f"{category} expected {expected_type.__name__}, got {type(result).__name__}"
        )
    return result


def _unwrap_llm(llm: LLMAdapter) -> LLMAdapter:
    if isinstance(llm, TelemetryLLMAdapter):
        return llm._inner
    return llm


def _format_tools_xml(tools: Sequence[Tool]) -> str:
    if not tools:
        return "（无可用工具）"
    lines = []
    for tool in tools:
        desc = tool.description or tool.name
        lines.append(f'<tool name="{tool.name}">{desc}</tool>')
    return "\n".join(lines)


def promote_lead(lead: CognitiveAgent, policy: BudgetPolicy) -> CognitiveAgent:
    limits = policy.resolve(lead)
    return CognitiveAgent(
        lead.runtime,
        lead.role_profile,
        lead.observability,
        max_steps=limits.max_steps,
        max_wall_clock_seconds=limits.max_wall_clock_seconds,
    )


def _instrument_llm(llm: LLMAdapter) -> LLMAdapter:
    return TelemetryLLMAdapter(_unwrap_llm(llm))


def _render_available_skills(scope: object) -> str:
    store = _skill_store_from_scope(scope)
    try:
        installed = store.list_installed()
    except Exception:
        return "（技能库不可用）"
    if not installed:
        return "（本地无已安装 skill，用 search_skill 从 Market 搜索）"
    return "\n".join(f"- {entry.skill_id}: {entry.name}" for entry in installed)


def _build_hooks(scope: object) -> Any:
    return require_capability(scope, HOOKS.key).create("simple")


def build_perceive_hub(
    memory: MemorySystem,
    *,
    hub: object | None = None,
    scope: object | None = None,
    action_scope: ActionScope | None = None,
) -> PerceiveHub:
    """Assemble PerceiveHub from the perceive group service on *scope*."""
    if scope is None or not callable(getattr(scope, "inject", None)):
        raise MissingCapabilityError("perceive")
    store_cls = _require_factory(scope, "journal_store")
    store = getattr(hub, "_run_store", None) or _run_store_from_scope(scope) or store_cls()
    team = _scope_is_team(action_scope) or _scope_is_team(scope)
    service = require_capability(scope, "perceive")
    skill_store = None
    members = service.members(team=team)
    if any(getattr(entry, "needs", None) == _NEEDS_SKILLS for entry in members):
        skill_store = _skill_store_from_scope(scope)
    return service.assemble(
        memory,
        store=store,
        skill_store=skill_store,
        team=team,
    )


def _build_middleware_registry(hooks: Any, scope: object) -> InMemoryMiddlewareRegistry:
    factory = _require_factory(scope, "middleware_registry.memory")
    registry = factory(hooks)
    if not isinstance(registry, InMemoryMiddlewareRegistry):
        raise TypeError(
            f"middleware_registry.memory expected InMemoryMiddlewareRegistry, "
            f"got {type(registry).__name__}"
        )
    return registry


def _apply_lead_brain(brain: Brain, *, decision_gate: DecisionGate) -> Brain:
    if not isinstance(brain, ModularBrain):
        raise TypeError(f"lead composition requires ModularBrain (got {type(brain).__name__})")
    return ModularBrain(
        reasoner=brain.reasoner,
        critic=brain.critic,
        skill_router=brain.skill_router,
        decision_gate=decision_gate,
        agent_gates=brain.agent_gates,
    )


def _resolve_memory(
    choice: str | MemorySystem,
    shared_store: SharedMemoryStore | None,
    memory_service: Any,
) -> MemorySystem:
    if shared_store is not None:
        mem: MemorySystem = memory_service.create(shared_store=shared_store)
    elif not isinstance(choice, str):
        mem = choice
    elif choice in memory_service.providers.names():
        mem = memory_service.providers.get(choice)()
    else:
        raise MissingCapabilityError("memory")
    return TelemetryMemoryAdapter(mem)


def _resolve_state_store(choice: str | StateStore, service: Any) -> StateStore:
    if not isinstance(choice, str):
        return choice
    if choice in service.providers.names():
        return service.providers.get(choice)()
    raise MissingCapabilityError("state_store")


def _resolve_brain(
    spec: AgentSpec,
    profile: RoleProfile,
    llm: LLMAdapter,
    *,
    scope: object,
) -> Brain:
    if not isinstance(spec.brain, str):
        return spec.brain
    brains = require_capability(scope, BRAINS.key)
    try:
        factory = brains.resolve(spec.brain)
    except KeyError as exc:
        raise ValueError(f"Unknown brain: {spec.brain!r}. Available: {brains.names()}") from exc
    resolved: Brain = factory(
        consume("llm", llm, PromptReasoner),
        profile,
        _format_tools_xml(spec.tools),
        tools=list(spec.tools),
        available_skills=_render_available_skills(scope),
    )
    return resolved


def _resolve_decision_gate(
    name: DecisionGateName,
    *,
    scope: object,
) -> DecisionGate | None:
    if name == DecisionGateName.NONE:
        return None
    if name == DecisionGateName.MUST_CONSULT_ALL:
        gates = require_capability(scope, "gates")
        result = gates.create("must-consult-all")
    else:
        components = require_capability(scope, COMPONENT_REGISTRY.key)
        factory = components.require(ComponentKind.DECISION_GATE, name)
        result = factory()
    if not isinstance(result, DecisionGate):
        raise TypeError(
            f"decision_gate factory produced {type(result).__name__}, expected DecisionGate"
        )
    return result


def _fork_transport(
    parent: Any,
    extra: AgentTransport | None,
    scope: object,
) -> Any:
    factory = _require_factory(scope, "transport.compose_service")
    child = factory()
    for protocol in parent.list_protocols():
        child.register(parent.resolve(protocol))
    if extra is not None:
        child.register(extra)
    return child


def spawn_agent(
    spec: AgentSpec,
    *,
    action_scope: ActionScope = ActionScope.SOLO,
    team_channel: AgentTransport | None = None,
    decision_gate: DecisionGate | None = None,
    shared_store: SharedMemoryStore | None = None,
    scope: Context | None = None,
) -> CognitiveAgent:
    """Close one AgentSpec into a CognitiveAgent from a booted capability scope."""
    scope = _ensure_scope(scope)
    profile = spec.profile
    if isinstance(spec.observability, str):
        hub = require_capability(scope, "observability").create()
    else:
        hub = create_observability(spec.observability)
    mem = _resolve_memory(
        spec.memory, shared_store, require_capability(scope, CapabilityKey.MEMORY.value)
    )
    state_store = _resolve_state_store(
        spec.state_store, require_capability(scope, CapabilityKey.STATE_STORE.value)
    )

    require_capability(scope, CapabilityKey.LLM.value)
    spec_llm = _instrument_llm(spec.llm)

    require_capability(scope, CapabilityKey.TOOLS.value)
    tools_factory = _require_factory(scope, "tools.compose_service")
    tool_registry = tools_factory()
    for tool in spec.tools:
        tool_registry.register(tool)
    safe_executor_cls = _require_factory(scope, "safe_executor.simple")
    safe_executor = safe_executor_cls(profile.tool_permission_manifest)
    transport_registry = _fork_transport(
        require_capability(scope, CapabilityKey.TRANSPORT.value), team_channel, scope
    )
    action_registry = build_default_action_registry(
        tool_registry,
        safe_executor,
        transport_registry,
        scope=action_scope,
    )

    brain = _resolve_brain(spec, profile, spec_llm, scope=scope)
    if decision_gate is not None:
        brain = _apply_lead_brain(brain, decision_gate=decision_gate)

    body = require_capability(scope, BODIES.key).create(
        "simple",
        tool_registry=tool_registry,
        safe_executor=safe_executor,
        transport_registry=transport_registry,
        action_registry=action_registry,
    )
    hooks = _build_hooks(scope)
    perceive_hub = build_perceive_hub(mem, hub=hub, scope=scope, action_scope=action_scope)
    stop_rule = require_capability(scope, STOP_RULES.key).create("default")
    runtime = build_cognitive_runtime(
        RuntimeDeps(
            brain=brain,
            body=body,
            memory=consume("memory", mem, CognitiveRuntime),
            hooks=hooks,
            state_store=consume("state_store", state_store, CognitiveRuntime),
            perceive_hub=perceive_hub,
            stop_rule=stop_rule,
            middleware_registry=_build_middleware_registry(hooks, scope),
        )
    )
    return CognitiveAgent(
        runtime,
        profile,
        hub,
        max_steps=spec.max_steps,
        max_wall_clock_seconds=spec.max_wall_clock_seconds,
    )


def spawn_lead(
    spec: AgentSpec,
    *,
    transport: AgentTransport,
    mandate: LeadMandate,
    observability: ObservabilityHub | None = None,
    scope: Context | None = None,
) -> CognitiveAgent:
    """Close a lead AgentSpec with mandate-specific decision gate."""
    scope = _ensure_scope(scope)
    lead_spec = replace(spec, observability=observability) if observability is not None else spec
    gate = _resolve_decision_gate(gate_name_for_mandate(mandate), scope=scope)
    composed = spawn_agent(
        lead_spec,
        action_scope=ActionScope.LEAD,
        team_channel=transport,
        decision_gate=gate,
        scope=scope,
    )
    components = require_capability(scope, COMPONENT_REGISTRY.key)
    policy = _resolve_component(
        components,
        ComponentKind.BUDGET_POLICY,
        LEAD_BUDGET_POLICY_KEY,
        BudgetPolicy,  # type: ignore[type-abstract]
    )
    return promote_lead(composed, policy)


def spawn_member(
    spec: AgentSpec,
    *,
    shared_store: SharedMemoryStore | None = None,
    observability: ObservabilityHub | None = None,
    scope: Context | None = None,
) -> CognitiveAgent:
    """Close a team member AgentSpec."""
    member_spec = replace(spec, observability=observability) if observability is not None else spec
    return spawn_agent(
        member_spec,
        action_scope=ActionScope.MEMBER,
        shared_store=shared_store,
        scope=scope,
    )


def _governance_from(lead: LeadSpec | None, coordination: Coordination | None) -> Governance:
    if lead is not None:
        if coordination is not None:
            raise ValueError("Team requires exactly one of lead= or coordination=")
        return lead
    if coordination is not None:
        return coordination
    raise ValueError("Team requires exactly one of lead= or coordination=")


def _build_stage(members: tuple[CognitiveAgent, ...]) -> tuple[TeamStage, AgentTransport]:
    roles = [member.role_profile.role for member in members]
    if any(not role for role in roles):
        raise ValueError("member role_profile.role is required for transport invoke")
    if len(set(roles)) != len(roles):
        raise ValueError(f"duplicate member roles in team: {sorted(roles)}")
    transport = build_team_transport(list(members))
    return TeamStage(members=members, invoker=TransportMemberInvoker(transport)), transport


def _trace_profile(
    strategy_key: str,
    governance: Governance,
    members: tuple[CognitiveAgent, ...],
    lead: AgentUnit | None,
) -> TeamTraceProfile:
    mandate = governance.mandate.value if isinstance(governance, LeadSpec) else None
    return TeamTraceProfile(
        team_id=team_id_for(strategy_key),
        strategy_key=strategy_key,
        mandate=mandate,
        lead_role=lead.role_profile.role if lead is not None else "",
        member_roles=tuple(member.role_profile.role for member in members),
    )


def _resolve_team_observability(spec: TeamSpec) -> ObservabilityHub:
    candidates: list[str | ObservabilityBackend] = []
    if spec.observability is not None:
        candidates.append(spec.observability)
    candidates.extend(member.observability for member in spec.members)
    governance = spec.governance
    if isinstance(governance, LeadSpec):
        candidates.append(governance.agent.observability)
    for choice in candidates:
        if isinstance(choice, ObservabilityHub):
            return choice
        if isinstance(choice, str):
            return create_observability(choice)
    return create_observability(OBSERVABILITY_CHOICE_CONSOLE)


def spawn_team(
    spec: TeamSpec | None = None,
    *,
    members: Sequence[AgentSpec] | None = None,
    lead: LeadSpec | None = None,
    coordination: Coordination | None = None,
    shared_memory_layers: Sequence[MemoryLayer] | None = None,
    delegate_max_attempts: int | None = None,
    observability: str | ObservabilityHub | None = None,
    scope: Context | None = None,
) -> TeamUnit:
    """Close a TeamSpec (or kwargs) into a TeamHandle."""
    scope = _ensure_scope(scope)
    if spec is None:
        if members is None:
            raise ValueError("spawn_team requires spec= or members=")
        governance = _governance_from(lead, coordination)
        spec = TeamSpec(
            members=tuple(members),
            governance=governance,
            shared_memory_layers=tuple(shared_memory_layers or ()),
            delegate_max_attempts=(
                delegate_max_attempts
                if delegate_max_attempts is not None
                else DEFAULT_DELEGATE_MAX_ATTEMPTS
            ),
            observability=observability,
        )
    shared_obs = _resolve_team_observability(spec)
    shared_store: SharedMemoryStore | None = (
        TeamSharedMemoryStore(list(spec.shared_memory_layers))
        if spec.shared_memory_layers
        else None
    )
    closed_members = tuple(
        spawn_member(
            member_spec,
            shared_store=shared_store,
            observability=shared_obs,
            scope=scope,
        )
        for member_spec in spec.members
    )
    stage, transport = _build_stage(closed_members)
    governance = spec.governance
    closed_lead: CognitiveAgent | None = None
    if isinstance(governance, LeadSpec):
        closed_lead = spawn_lead(
            governance.agent,
            transport=transport,
            mandate=governance.mandate,
            observability=shared_obs,
            scope=scope,
        )
    assembly = TeamAssembly(
        governance=governance,
        stage=stage,
        lead=closed_lead,
        delegate_max_attempts=spec.delegate_max_attempts,
    )
    strategy_key = strategy_key_for_governance(spec.governance)
    strategy = require_capability(scope, STRATEGIES.key).create(strategy_key, assembly)
    profile = _trace_profile(strategy_key, spec.governance, closed_members, assembly.lead)
    return TeamHandle(strategy, profile, shared_obs, closed_members, assembly.lead)
