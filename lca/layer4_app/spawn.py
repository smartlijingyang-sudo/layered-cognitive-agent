"""L4 spawn — close AgentSpec / TeamSpec into live object graphs.

ADR-0056: group services assemble contributions; this module binds the
per-agent spec and builds CognitiveRuntime / TeamHandle. No Composer
class. No contribution-id lists.
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
    HookEvent,
    MemoryLayer,
)
from lca.contracts.mechanisms import ComponentRegistryProtocol, consume
from lca.contracts.mechanisms.capability import (
    CapabilityKey,
    MissingCapabilityError,
    provider_current,
    require_capability,
)
from lca.contracts.mechanisms.registries import Registries
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
    BRAIN_CHOICE_DEFAULT,
    DEFAULT_DELEGATE_MAX_ATTEMPTS,
    OBSERVABILITY_CHOICE_CONSOLE,
    AgentSpec,
    Governance,
    LeadSpec,
    TeamSpec,
    strategy_key_for_governance,
)
from lca.harness.middleware import InMemoryMiddlewareRegistry
from lca.layer0_infra.capability.memory import MemoryService
from lca.layer0_infra.capability.state_store import StateStoreService
from lca.layer0_infra.capability.tools import ToolsService
from lca.layer0_infra.capability.transport import TransportService
from lca.layer0_infra.observability import (
    ObservabilityHub,
    TeamTraceProfile,
    create_observability,
    team_id_for,
)
from lca.layer0_infra.observability import record as _journal_record
from lca.layer0_infra.observability.adapters import TelemetryLLMAdapter, TelemetryMemoryAdapter
from lca.layer1_cognitive.body.action_catalog import build_default_action_registry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.brain.decision_gates import MustConsultAllMembers
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import PromptReasoner
from lca.layer1_cognitive.gate_service import GateService
from lca.layer1_cognitive.hook_registry import SimpleHookRegistry, default_logging_hook
from lca.layer1_cognitive.memory.team_shared_memory import TeamSharedMemoryStore
from lca.layer1_cognitive.perceive_service import (
    Needs,
    PerceiveService,
    register_builtin_sensors,
)
from lca.layer2_runtime.default_stop_rule import DefaultStopRule
from lca.layer2_runtime.event_emission import make_journal_emitting_hook
from lca.layer2_runtime.outcome_policies.default_outcome_policy import DefaultStopOutcomePolicy
from lca.layer2_runtime.runtime_loop import CognitiveRuntime
from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer3_agent.member_invoke import TransportMemberInvoker
from lca.layer3_agent.team_handle import TeamHandle
from lca.layer4_app.defaults import build_default_registries
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
_NEEDS_SKILLS: Needs = "skills"


class _ScopeAsCapabilityContext:
    """Adapter: cordis.Context where CapabilityHub.require/get/mount is expected."""

    def __init__(self, ctx: Any) -> None:
        self._ctx = ctx

    def require(self, key: str) -> Any:
        result = self._ctx.inject(key)
        if result is None:
            raise MissingCapabilityError(key)
        return result

    def get(self, key: str) -> Any | None:
        return self._ctx.inject(key)

    def mount(self, key: str, service: Any) -> None:
        self._ctx.provide(key, service)

    def keys(self) -> list[str]:
        return [k for k in dir(self._ctx) if not k.startswith("_")]


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


def _is_plugin_tree(scope: object | None) -> bool:
    return callable(getattr(scope, "inject", None))


def _ctx_factory(scope: object | None, key: str) -> Any | None:
    inject = getattr(scope, "inject", None)
    if not callable(inject):
        return None
    try:
        return inject(key)
    except Exception:
        return None


def _resolve_named_factory(scope: object | None, key: str, standard: Any | None) -> Any | None:
    if _is_plugin_tree(scope):
        return _ctx_factory(scope, key)
    return standard


def _skill_store_from_scope(scope: object | None) -> Any:
    if _is_plugin_tree(scope):
        store = provider_current(require_capability(scope, "skills"))
        if store is None:
            raise MissingCapabilityError("skills")
        return store
    from lca.layer0_infra.skills.factory import resolve_skill_store

    return resolve_skill_store()


def _resolve_component(
    reg: ComponentRegistryProtocol,
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


def _render_available_skills(scope: object | None = None) -> str:
    if not _is_plugin_tree(scope):
        return "（技能库不可用）"
    store = _skill_store_from_scope(scope)
    try:
        installed = store.list_installed()
    except Exception:
        return "（技能库不可用）"
    if not installed:
        return "（本地无已安装 skill，用 search_skill 从 Market 搜索）"
    return "\n".join(f"- {entry.skill_id}: {entry.name}" for entry in installed)


def _standard_hooks() -> SimpleHookRegistry:
    hooks = SimpleHookRegistry()
    journal_hook = make_journal_emitting_hook(_journal_record)
    for event_name in HookEvent:
        hooks.register(event_name, default_logging_hook)
        hooks.register(event_name, journal_hook)
    return hooks


def _build_hooks(scope: object | None = None) -> SimpleHookRegistry:
    factory = _resolve_named_factory(scope, "hook_registry.simple", None)
    if factory is not None:
        hooks = factory()
        if isinstance(hooks, SimpleHookRegistry):
            return hooks
    return _standard_hooks()


def build_perceive_hub(
    memory: MemorySystem,
    *,
    hub: object | None = None,
    scope: object | None = None,
    action_scope: ActionScope | None = None,
) -> PerceiveHub:
    """Assemble PerceiveHub from the perceive group (or builtin sensors)."""
    from lca.layer0_infra.observability import RunStore

    store_cls = _resolve_named_factory(scope, "journal_store", RunStore)
    store = (
        getattr(hub, "_run_store", None)
        or _run_store_from_scope(scope)
        or (store_cls() if store_cls is not None else RunStore())
    )
    team = _scope_is_team(action_scope) or _scope_is_team(scope)
    service = _resolve_named_factory(scope, "perceive", None)
    if service is None:
        if _is_plugin_tree(scope):
            raise MissingCapabilityError("perceive")
        service = PerceiveService()
        register_builtin_sensors(service)
    if not isinstance(service, PerceiveService):
        raise TypeError(f"perceive expected PerceiveService, got {type(service).__name__}")
    skill_store = None
    if any(entry.needs == _NEEDS_SKILLS for entry in service.members(team=team)):
        skill_store = _skill_store_from_scope(scope)
    return service.assemble(
        memory,
        store=store,
        skill_store=skill_store,
        team=team,
    )


def _build_middleware_registry(
    hooks: SimpleHookRegistry,
    scope: object | None = None,
) -> InMemoryMiddlewareRegistry:
    from lca.layer2_runtime.hook_middleware import install_hook_bridge

    factory = _resolve_named_factory(scope, "middleware_registry.memory", None)
    if factory is not None:
        registry = factory(hooks)
        if isinstance(registry, InMemoryMiddlewareRegistry):
            return registry
    registry = InMemoryMiddlewareRegistry()
    install_hook_bridge(registry, hooks)
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
    memory_service: MemoryService,
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


def _resolve_state_store(choice: str | StateStore, service: StateStoreService) -> StateStore:
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
    scope: Context | None = None,
    registries: Registries,
) -> Brain:
    if not isinstance(spec.brain, str):
        return spec.brain
    if _is_plugin_tree(scope):
        brain_key = spec.brain
        factory = _resolve_named_factory(scope, f"brain_factory.{brain_key}", None)
        if factory is None:
            factory = _resolve_named_factory(scope, "brain_factory", None)
            if factory is None or brain_key != BRAIN_CHOICE_DEFAULT:
                raise ValueError(
                    f"Unknown brain: {spec.brain!r}. Available: "
                    "brain_factory.default, brain_factory.modular"
                )
    else:
        factory_reg = registries.brain_factories
        if spec.brain not in factory_reg:
            raise ValueError(f"Unknown brain: {spec.brain!r}. Available: {factory_reg.list()}")
        factory = factory_reg.resolve(spec.brain)
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
    scope: object | None = None,
    registries: Registries,
) -> DecisionGate | None:
    if name == DecisionGateName.NONE:
        return None
    if name == DecisionGateName.MUST_CONSULT_ALL:
        gates = _resolve_named_factory(scope, "gates", None)
        if isinstance(gates, GateService):
            return gates.create("must-consult-all")
        factory = _resolve_named_factory(scope, "gate.must-consult-all", MustConsultAllMembers)
        if factory is None:
            raise MissingCapabilityError("gates")
        result = factory() if callable(factory) else factory
    else:
        factory = registries.components.require(ComponentKind.DECISION_GATE, name)
        result = factory()
    if not isinstance(result, DecisionGate):
        raise TypeError(
            f"decision_gate factory produced {type(result).__name__}, expected DecisionGate"
        )
    return result


def _fork_transport(
    parent: TransportService,
    extra: AgentTransport | None,
    scope: object | None,
) -> TransportService:
    factory = _resolve_named_factory(scope, "transport.compose_service", None)
    if factory is None:
        factory = TransportService
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
    registries: Registries | None = None,
) -> CognitiveAgent:
    """Close one AgentSpec into a CognitiveAgent."""
    if scope is None:
        from lca.layer4_app.api import get_or_create_default_ctx

        scope = get_or_create_default_ctx()
    regs = registries if registries is not None else build_default_registries()
    profile = spec.profile
    ctx = _ScopeAsCapabilityContext(scope)
    if _is_plugin_tree(scope) and isinstance(spec.observability, str):
        hub = require_capability(scope, "observability").create()
    else:
        hub = create_observability(spec.observability)
    mem = _resolve_memory(spec.memory, shared_store, ctx.require(CapabilityKey.MEMORY.value))
    state_store = _resolve_state_store(
        spec.state_store, ctx.require(CapabilityKey.STATE_STORE.value)
    )

    ctx.require(CapabilityKey.LLM.value)
    spec_llm = _instrument_llm(spec.llm)

    ctx.require(CapabilityKey.TOOLS.value)
    tools_factory = _resolve_named_factory(scope, "tools.compose_service", None)
    if tools_factory is None:
        tools_factory = ToolsService
    tool_registry = tools_factory()
    for tool in spec.tools:
        tool_registry.register(tool)
    safe_executor_cls = _resolve_named_factory(scope, "safe_executor.simple", SimpleSafeExecutor)
    if safe_executor_cls is None:
        raise MissingCapabilityError("safe_executor.simple")
    safe_executor = safe_executor_cls(profile.tool_permission_manifest)
    transport_registry = _fork_transport(
        ctx.require(CapabilityKey.TRANSPORT.value), team_channel, scope
    )
    action_registry = build_default_action_registry(
        tool_registry,
        safe_executor,
        transport_registry,
        scope=action_scope,
    )

    brain = _resolve_brain(spec, profile, spec_llm, scope=scope, registries=regs)
    if decision_gate is not None:
        brain = _apply_lead_brain(brain, decision_gate=decision_gate)

    body_cls = _resolve_named_factory(scope, "body.simple", SimpleBody)
    if body_cls is None:
        raise MissingCapabilityError("body.simple")
    body = body_cls(
        tool_registry=tool_registry,
        safe_executor=safe_executor,
        transport_registry=transport_registry,
        action_registry=action_registry,
    )
    hooks = _build_hooks(scope)
    perceive_hub = build_perceive_hub(mem, hub=hub, scope=scope, action_scope=action_scope)
    stop_factory = _resolve_named_factory(
        scope,
        "stop_rule.default",
        lambda: DefaultStopRule(outcome_policy=DefaultStopOutcomePolicy()),
    )
    if stop_factory is None:
        raise MissingCapabilityError("stop_rule.default")
    runtime = build_cognitive_runtime(
        RuntimeDeps(
            brain=brain,
            body=body,
            memory=consume("memory", mem, CognitiveRuntime),
            hooks=hooks,
            state_store=consume("state_store", state_store, CognitiveRuntime),
            perceive_hub=perceive_hub,
            stop_rule=stop_factory(),
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
    registries: Registries | None = None,
) -> CognitiveAgent:
    """Close a lead AgentSpec with mandate-specific decision gate."""
    regs = registries if registries is not None else build_default_registries()
    lead_spec = replace(spec, observability=observability) if observability is not None else spec
    gate = _resolve_decision_gate(gate_name_for_mandate(mandate), scope=scope, registries=regs)
    composed = spawn_agent(
        lead_spec,
        action_scope=ActionScope.LEAD,
        team_channel=transport,
        decision_gate=gate,
        scope=scope,
        registries=regs,
    )
    policy = _resolve_component(
        regs.components,
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
    registries: Registries | None = None,
) -> CognitiveAgent:
    """Close a team member AgentSpec."""
    member_spec = replace(spec, observability=observability) if observability is not None else spec
    return spawn_agent(
        member_spec,
        action_scope=ActionScope.MEMBER,
        shared_store=shared_store,
        scope=scope,
        registries=registries,
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
    registries: Registries | None = None,
) -> TeamUnit:
    """Close a TeamSpec (or kwargs) into a TeamHandle."""
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
    regs = registries if registries is not None else build_default_registries()
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
            registries=regs,
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
            registries=regs,
        )
    assembly = TeamAssembly(
        governance=governance,
        stage=stage,
        lead=closed_lead,
        delegate_max_attempts=spec.delegate_max_attempts,
    )
    strategy_key = strategy_key_for_governance(spec.governance)
    strategy = regs.orchestration.resolve(strategy_key, assembly)
    profile = _trace_profile(strategy_key, spec.governance, closed_members, assembly.lead)
    return TeamHandle(strategy, profile, shared_obs, closed_members, assembly.lead)
