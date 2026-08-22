"""Bind a CompiledRunPlan to complete AgentGraph and TeamGraph instances."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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


def bind_plan(
    request: AgentCompositionRequest,
    plan: CompiledRunPlan,
    *,
    scope: Context,
) -> PlanBindingResult:
    """Bind every required Agent composer and validate the capability plan."""

    from lca.contracts.harness.composer import merge_agent_graphs

    composer_keys = ("brain", "body", "perceive")
    graphs = tuple(
        _resolve_composer(scope, key).compose_agent(request, scope) for key in composer_keys
    )
    graph = merge_agent_graphs(*graphs)
    _validate_capability_bindings(plan, graph, scope)
    return PlanBindingResult(
        graph=graph,
        plan_ref=compiled_run_plan_ref(plan),
        plan=plan,
        metadata={"composers": composer_keys},
    )


def bind_team(
    spec: TeamSpec,
    plan: CompiledRunPlan,
    *,
    scope: Context,
) -> TeamBindingResult:
    """Bind the required Team composer and reject every incomplete TeamGraph."""

    graph = _resolve_composer(scope, "team").compose_team(spec, scope)
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
        metadata={"composer": "team"},
    )


def _resolve_composer(scope: Context, key: str) -> Any:
    """Resolve a required profile-provided Composer or fail the binding."""

    inject = getattr(scope, "inject", None)
    if not callable(inject):
        raise BindPlanError("plan binding requires a booted cordis Context with inject()")
    try:
        composer = inject(f"composer.{key}")
    except (KeyError, LookupError) as exc:
        raise BindPlanError(
            f"required composer.{key} is not registered in the booted Profile"
        ) from exc
    if composer is None:
        raise BindPlanError(f"required composer.{key} resolved to None")
    return composer


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


__all__ = ["BindPlanError", "PlanBindingResult", "TeamBindingResult", "bind_plan", "bind_team"]
