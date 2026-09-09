"""Bundle-relative ``SubgraphResolver`` for compile-time and runtime plan lookup."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphResolver,
)
from lca.contracts.protocols.state.plan import COMPILED_RUN_PLAN_VERSION, CompiledRunPlan
from lca.contracts.protocols.state.scope_plan import BudgetCeiling, ScopePlan
from lca.harness.declarative.compile.compiler.compiler import compile_declarative_projection
from lca.harness.declarative.controls.validation import PhaseGraphValidator, require_valid
from lca.harness.plan import build_input_provenance
from lca.harness.profile.plan.projection import ProfileCompilationProjections
from lca.harness.profile.resolve.capability_plan_resolver import (
    CapabilityPlanOptions,
    project_capability_plan,
)
from lca.harness.profile.resolve.resolve import ResolvedProfile, resolve_profile

# Bundle path → fixture profile that compiles the subgraph in isolation.
# Profiles live under ``profiles/fixtures/`` and are not production defaults.
_PLAN_REF_PROFILES: Final[dict[str, str]] = {
    "bundles/think-subgraph.yaml": "profiles/fixtures/think-subgraph-compile.yaml",
    "bundles/think-orchestrator.yaml": "profiles/fixtures/think-orchestrator-compile.yaml",
    "bundles/reflect-subgraph.yaml": "profiles/fixtures/reflect-subgraph-compile.yaml",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _compile_subgraph_fixture(resolved: ResolvedProfile) -> CompiledRunPlan:
    """Compile one subgraph fixture profile without production runtime closure.

    Subgraph bundles only need the declarative phase graph projection. They
    must not pull in the full production runtime seam closure that a
    runnable profile like ``web-standard`` requires.
    """

    projections = ProfileCompilationProjections.build(resolved)
    declarative = compile_declarative_projection(
        resolved,
        task_contract="subgraph-fixture",
        environment="subgraph-fixture",
        actor_grant=(),
        projection=projections.selected,
    )
    if declarative.phase_graph is None:
        raise ValueError(
            f"subgraph fixture profile {resolved.profile_path!r} produced no phase graph"
        )
    subgraph_report = PhaseGraphValidator().validate(
        declarative.phase_graph,
        declarative.phase_bindings,
        declarative.plugin_specs,
        declarative.effect_policy,
        require_all_semantic_phases=False,
    )
    require_valid(subgraph_report)
    capability = project_capability_plan(
        resolved,
        options=CapabilityPlanOptions(),
        projection=projections.selected,
    )
    scope = ScopePlan(
        profile_path=resolved.profile_path,
        lifecycle=Scope.RUN,
        visibility=tuple(Scope),
        acl_grants=(),
        budget_ceiling=BudgetCeiling(),
        revision="v1",
    )
    input_provenance = build_input_provenance(
        profile_path=resolved.profile_path,
        bundles=resolved.bundles,
        patches=(),
        task_id=None,
        env_fingerprint=None,
    )
    return CompiledRunPlan(
        profile_path=resolved.profile_path,
        capability=capability,
        scope=scope,
        plan_version=COMPILED_RUN_PLAN_VERSION,
        input_provenance=input_provenance,
        revision="v3",
        plugin_specs=declarative.plugin_specs,
        capability_bindings=declarative.capability_bindings,
        phase_graph=declarative.phase_graph,
        phase_bindings=declarative.phase_bindings,
        control_entries=declarative.control_entries,
        replacement_map=declarative.replacement_map,
        effect_policy=declarative.effect_policy,
        action_authority=declarative.action_authority,
        provenance=declarative.provenance,
        validation_report=subgraph_report,
    )


@lru_cache(maxsize=16)
def _compile_subgraph_profile(relative_profile: str) -> CompiledRunPlan:
    profile_path = _repo_root() / relative_profile
    resolved = resolve_profile(profile_path)
    return _compile_subgraph_fixture(resolved)


class BundleSubgraphResolver:
    """Resolve ``SubgraphReference.plan_ref`` bundle paths to ``CompiledRunPlan``.

    The resolver owns a small, explicit map from bundle-relative paths to
    fixture profiles that compile each subgraph bundle. Results are cached
    per process so repeated edge recursion and host executors do not
    re-compile on every visit.
    """

    def resolve(self, plan_ref: str) -> CompiledRunPlan | None:
        relative_profile = _PLAN_REF_PROFILES.get(plan_ref)
        if relative_profile is None:
            return None
        return _compile_subgraph_profile(relative_profile)


def default_subgraph_resolver() -> SubgraphResolver:
    """Return the production bundle-relative subgraph resolver."""

    return BundleSubgraphResolver()


__all__ = [
    "BundleSubgraphResolver",
    "default_subgraph_resolver",
]
