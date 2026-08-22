"""Bind a CompiledRunPlan to complete AgentGraph and TeamGraph instances."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lca.contracts.mechanisms.capability import MissingCapabilityError
from lca.contracts.protocols.plan import compiled_run_plan_ref

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.harness.composer import AgentGraph, TeamGraph
    from lca.contracts.protocols.plan import CompiledRunPlan
    from lca.contracts.protocols.spec import TeamSpec
    from lca.plugins.composer.plan_composition_support import AgentCompositionRequest


@dataclass(frozen=True, slots=True)
class PlanBindingResult:
    """The complete AgentGraph and immutable plan selected for one Agent."""

    graph: AgentGraph
    plan_ref: str
    plan: CompiledRunPlan
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TeamBindingResult:
    """The complete TeamGraph and immutable plan selected for one Team."""

    graph: TeamGraph
    plan_ref: str
    plan: CompiledRunPlan
    metadata: dict[str, Any] = field(default_factory=dict)


class BindPlanError(ValueError):
    """A booted Profile cannot satisfy the complete plan-binding contract."""


def compiled_plan_from_scope(scope: Context) -> CompiledRunPlan:
    """Compile the resolved boot profile into the single runnable input plan."""

    resolved = getattr(scope, "resolved_profile", None)
    if resolved is None:
        raise MissingCapabilityError("resolved_profile")
    from lca.harness.profile.plan_compiler import compile_plan

    return compile_plan(resolved)


def bind_plan(
    request: AgentCompositionRequest,
    plan: CompiledRunPlan,
    *,
    scope: Context,
) -> PlanBindingResult:
    """Bind every required Agent composer and validate the capability plan."""

    from lca.contracts.harness.composer import merge_agent_graphs

    composer_bindings = _composer_bindings(plan, scope, operation="compose_agent")
    composed = []
    for capability, composer in composer_bindings:
        try:
            composed.append((capability, composer.compose_agent(request, scope)))
        except TypeError:
            # The Protocol implementation rejects an unsupported composition kind.
            # This is capability behavior, not an implementation identity branch.
            continue
    if not composed:
        raise BindPlanError("compiled plan declares no Agent composer capability")
    graph = merge_agent_graphs(*(item[1] for item in composed))
    _validate_capability_bindings(plan, graph, scope)
    return PlanBindingResult(
        graph=graph,
        plan_ref=compiled_run_plan_ref(plan),
        plan=plan,
        metadata={
            "composers": tuple(capability for capability, _ in composed)
        },
    )


def bind_team(
    spec: TeamSpec,
    plan: CompiledRunPlan,
    *,
    scope: Context,
) -> TeamBindingResult:
    """Bind the required Team composer and reject every incomplete TeamGraph."""

    team_candidates = _composer_bindings(plan, scope, operation="compose_team")
    team_composers = []
    for capability, composer in team_candidates:
        try:
            team_composers.append((capability, composer.compose_team(spec, scope)))
        except TypeError:
            continue
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
    _validate_capability_bindings(plan, graph, scope)
    return TeamBindingResult(
        graph=graph,
        plan_ref=compiled_run_plan_ref(plan),
        plan=plan,
        metadata={
            "composer": team_composers[0][0]
        },
    )


def _composer_bindings(
    plan: CompiledRunPlan,
    scope: Context,
    *,
    operation: str,
) -> tuple[tuple[str, Any], ...]:
    """Discover composer capabilities solely from the compiled plan.

    The binding algorithm knows the composer *Protocol* operation but no concrete
    composer key, factory identity or implementation name.
    """

    inject = getattr(scope, "inject", None)
    if not callable(inject):
        raise BindPlanError("plan binding requires a booted cordis Context with inject()")
    
    # ADR-0074/0075: Only declarative plans are supported
    if not plan.is_declarative:
        raise BindPlanError(
            "Non-declarative compiled plans are not supported. "
            "All production plans must be declarative (ADR-0074/0075)."
        )
    
    declared_capabilities = {binding.capability for binding in plan.capability_bindings}
    candidates = sorted(
        capability
        for capability in declared_capabilities
        if capability.startswith("composer.")
    )
    resolved: list[tuple[str, Any]] = []
    for capability in candidates:
        try:
            composer = inject(capability)
        except (KeyError, LookupError):
            continue
        if composer is not None and callable(getattr(composer, operation, None)):
            resolved.append((capability, composer))
    return tuple(resolved)


def _validate_capability_bindings(
    plan: CompiledRunPlan,
    graph: AgentGraph | TeamGraph,
    scope: Context,
) -> None:
    """Require every provider binding declared by the compiled plan to resolve."""

    del graph
    inject = getattr(scope, "inject", None)
    if not callable(inject):
        raise BindPlanError("capability validation requires a booted cordis Context with inject()")
    for binding in plan.capability.provider_bindings:
        capability = binding.capability
        registry_key = capability.split("[", 1)[0]
        candidates = tuple(
            dict.fromkeys(
                (
                    capability,
                    registry_key,
                    registry_key.split(".", 1)[0] if "." in registry_key else registry_key,
                )
            )
        )
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                inject(candidate)
                break
            except (KeyError, LookupError) as error:
                last_error = error
        else:
            raise BindPlanError(
                f"capability {capability!r} (owner={binding.owner_plugin!r}) has no resolvable "
                f"registry among {candidates!r}: {last_error}"
            ) from last_error


__all__ = [
    "BindPlanError",
    "PlanBindingResult",
    "TeamBindingResult",
    "bind_plan",
    "bind_team",
    "compiled_plan_from_scope",
]
