"""Bind a CompiledRunPlan to complete AgentGraph and TeamGraph instances."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lca.contracts.atoms.enums import ActionScope
from lca.contracts.harness.composition.composer import (
    AgentCompositionRequest,
    AgentGraphComposer,
    TeamGraphComposer,
)
from lca.harness.declarative.authority import action_authority_for_scope
from lca.harness.plan import compiled_run_plan_ref
from lca.harness.profile.boot_products import compiled_plan_from_scope
from lca.plugins.composer.composition.capability_resolution import (
    CapabilityResolutionError,
    ScopeCapabilityResolver,
)

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.harness.composition.composer import AgentGraph, TeamGraph
    from lca.contracts.protocols import DecisionGate, SharedMemoryStore
    from lca.contracts.protocols.journal.spec import AgentSpec, TeamSpec
    from lca.contracts.protocols.runtime.infra import AgentTransport
    from lca.contracts.protocols.state.plan import CompiledRunPlan


@dataclass(frozen=True, slots=True)
class PlanBindingResult:
    """The complete AgentGraph and immutable plan selected for one Agent."""

    graph: AgentGraph
    plan_ref: str
    plan: CompiledRunPlan
    composer_capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TeamBindingResult:
    """The complete TeamGraph and immutable plan selected for one Team."""

    graph: TeamGraph
    plan_ref: str
    plan: CompiledRunPlan
    composer_capability: str


class BindPlanError(ValueError):
    """A booted Profile cannot satisfy the complete plan-binding contract."""


def bind_agent_from_scope(
    spec: AgentSpec,
    *,
    action_scope: ActionScope = ActionScope.SOLO,
    team_channel: AgentTransport | None = None,
    decision_gate: DecisionGate | None = None,
    shared_store: SharedMemoryStore | None = None,
    scope: Context,
) -> PlanBindingResult:
    """Bind one Agent from the immutable plan frozen during profile boot.

    The binder owns the complete ``scope → plan → authority → request → graph``
    sequence. Production composition therefore cannot reinterpret a plan or
    duplicate action-authority projection outside this seam. ``bind_plan``
    remains available for tests that construct an explicit fixture plan.
    """

    plan = compiled_plan_from_scope(scope)
    authority = plan.action_authority
    if authority is None:
        raise BindPlanError(
            "compiled plan is missing required action_authority; "
            "production Agents must receive plan-derived action permissions"
        )
    scoped_authority = action_authority_for_scope(authority, action_scope)
    return bind_plan(
        AgentCompositionRequest(
            spec=spec,
            action_scope=action_scope,
            team_channel=team_channel,
            decision_gate=decision_gate,
            shared_store=shared_store,
            allowed_actions=scoped_authority.allowed_actions,
            forbidden_actions=scoped_authority.forbidden_actions,
        ),
        plan,
        scope=scope,
    )


def bind_team_from_scope(
    spec: TeamSpec,
    *,
    scope: Context,
) -> TeamBindingResult:
    """Bind one Team using only the immutable plan frozen during profile boot.

    Production callers must not resolve or forward a plan independently.  This
    keeps Agent and Team composition on the same single-source boundary while
    preserving ``bind_team`` for tests that construct an explicit fixture plan.
    """

    return bind_team(spec, compiled_plan_from_scope(scope), scope=scope)


def bind_plan(
    request: AgentCompositionRequest,
    plan: CompiledRunPlan,
    *,
    scope: Context,
) -> PlanBindingResult:
    """Bind every required Agent composer and validate the capability plan."""

    from lca.contracts.harness.composition.composer import merge_agent_graphs

    _validate_capability_bindings(plan, scope)
    composer_bindings = _agent_composer_bindings(plan, scope)
    composed = [
        (capability, composer.compose_agent(request, scope))
        for capability, composer in composer_bindings
    ]
    if not composed:
        raise BindPlanError("compiled plan declares no Agent composer capability")
    try:
        graph = merge_agent_graphs(*(item[1] for item in composed))
    except ValueError as exc:
        raise BindPlanError(f"bind_plan: {exc}") from exc
    return PlanBindingResult(
        graph=graph,
        plan_ref=compiled_run_plan_ref(plan),
        plan=plan,
        composer_capabilities=tuple(capability for capability, _ in composed),
    )


def bind_team(
    spec: TeamSpec,
    plan: CompiledRunPlan,
    *,
    scope: Context,
) -> TeamBindingResult:
    """Bind the required Team composer and reject every incomplete TeamGraph."""

    _validate_capability_bindings(plan, scope)
    team_candidates = _team_composer_bindings(plan, scope)
    team_composers = [
        (capability, composer.compose_team(spec, scope)) for capability, composer in team_candidates
    ]
    if len(team_composers) != 1:
        raise BindPlanError(
            "compiled plan must resolve exactly one Team composer capability; "
            f"got {[capability for capability, _ in team_composers]!r}"
        )
    graph = team_composers[0][1]
    missing = tuple(
        name
        for name in ("members", "strategy", "stage", "transport", "observability")
        if getattr(graph, name, None) is None or (name == "members" and not graph.members)
    )
    if missing:
        raise BindPlanError(
            "bind_team: TeamComposer returned an incomplete TeamGraph: " + ", ".join(missing)
        )
    return TeamBindingResult(
        graph=graph,
        plan_ref=compiled_run_plan_ref(plan),
        plan=plan,
        composer_capability=team_composers[0][0],
    )


def _agent_composer_bindings(
    plan: CompiledRunPlan,
    scope: Context,
) -> tuple[tuple[str, AgentGraphComposer], ...]:
    """Resolve plan-declared capabilities that contribute partial Agent graphs."""

    return tuple(
        (capability, composer)
        for capability, composer in _composer_candidates(plan, scope)
        if isinstance(composer, AgentGraphComposer)
    )


def _team_composer_bindings(
    plan: CompiledRunPlan,
    scope: Context,
) -> tuple[tuple[str, TeamGraphComposer], ...]:
    """Resolve the plan-declared capabilities that can contribute a TeamGraph."""

    return tuple(
        (capability, composer)
        for capability, composer in _composer_candidates(plan, scope)
        if isinstance(composer, TeamGraphComposer)
    )


def _composer_candidates(
    plan: CompiledRunPlan,
    scope: Context,
) -> tuple[tuple[str, object], ...]:
    """Resolve the plan-declared composer capabilities without invoking them.

    ``composer.*`` is reserved for graph composers; unrelated construction
    factories belong to their own capability namespace.  The narrow Protocol
    checks here classify every declared graph composer before invocation, so
    each capability has exactly one eligible graph shape.  Binding rejects a
    missing, empty, or ambiguous declaration before invoking any composer
    instead of silently treating a partial graph as an implementation failure.
    """

    resolver = _scope_capabilities(scope, purpose="plan binding")

    declared_capabilities = {binding.capability for binding in plan.capability_bindings}
    candidates = sorted(
        capability for capability in declared_capabilities if capability.startswith("composer.")
    )
    resolved: list[tuple[str, object]] = []
    for capability in candidates:
        try:
            composer = resolver.require_exact(capability)
        except CapabilityResolutionError as exc:
            raise BindPlanError(
                f"compiled plan declares unavailable composer capability {capability!r}"
            ) from exc
        if composer is None:
            raise BindPlanError(f"compiled plan declares empty composer capability {capability!r}")
        is_agent_composer = isinstance(composer, AgentGraphComposer)
        is_team_composer = isinstance(composer, TeamGraphComposer)
        if is_agent_composer == is_team_composer:
            implemented = "neither" if not is_agent_composer else "both"
            raise BindPlanError(
                f"compiled plan declares graph composer capability {capability!r} whose provider "
                f"implements {implemented} AgentGraphComposer and TeamGraphComposer; "
                "every composer capability must implement exactly one graph-composition protocol"
            )
        resolved.append((capability, composer))
    return tuple(resolved)


def _validate_capability_bindings(plan: CompiledRunPlan, scope: Context) -> None:
    """Fail closed on every declared provider before any graph is composed.

    Provider resolution belongs to the immutable compiled plan, not to an
    already-partial AgentGraph or TeamGraph.  Each binding carries the one
    scope key that its provider exposes; this seam must not infer alternate
    registry or namespace keys from a descriptive capability name.  Validating
    those explicit keys first keeps plan binding atomic: a rejected plan cannot
    invoke a composer and leave construction work whose failure origin is
    ambiguous.
    """

    resolver = _scope_capabilities(scope, purpose="capability validation")
    for binding in plan.capability.provider_bindings:
        capability = binding.capability
        try:
            resolver.require_provider_binding(binding)
        except CapabilityResolutionError as exc:
            raise BindPlanError(
                f"capability {capability!r} (owner={binding.owner_plugin!r}) cannot be resolved: "
                f"{exc}"
            ) from exc


def _scope_capabilities(scope: Context, *, purpose: str) -> ScopeCapabilityResolver:
    """Create the one scope adapter used by plan binding operations."""

    try:
        return ScopeCapabilityResolver.from_scope(scope)
    except CapabilityResolutionError as exc:
        raise BindPlanError(f"{purpose} requires a booted cordis Context with inject()") from exc


__all__ = [
    "BindPlanError",
    "PlanBindingResult",
    "TeamBindingResult",
    "bind_agent_from_scope",
    "bind_plan",
    "bind_team",
    "bind_team_from_scope",
    "compiled_plan_from_scope",
]
