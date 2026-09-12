"""V2 kernel-native plan compilation (replaces
``lca.harness.composition.plan_compiler.compile_plan``).

The v1 plan compiler emitted ``phase_graph`` + ``phase_bindings`` regions
that the v0 ``GraphAssembler`` consumed. ADR-0221 P3 retires those
regions: the v2 runtime builds its executable plan directly from
``PlanInterpreter`` + NodeExecutor subgraphs, so the compiled plan no
longer carries a declarative phase graph. This module emits a v2 plan
with ``phase_graph=None`` and an empty ``phase_bindings`` tuple.

Replaces ``lca.harness.composition.plan_compiler``. The ``CompileOptions``
shape is preserved so existing callers (kernel boot, tests) continue to
work; only the v1-only fields are no-ops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    ActionAuthorityPlan,
)
from lca.contracts.protocols.state.plan import (
    COMPILED_RUN_PLAN_VERSION,
    CompiledRunPlan,
)
from lca.contracts.protocols.state.scope_plan import BudgetCeiling, ScopePlan
from lca.harness.profile.resolve.capability_plan_resolver import (
    CapabilityPlanOptions,
    project_capability_plan,
)
from lca.harness.profile.resolve.resolve import ResolvedProfile


class PlanCompilerError(ValueError):
    """PlanCompiler 编译失败（profile 不合法 / 子 plan 投影失败）。"""


@dataclass(frozen=True, slots=True)
class V2ExecutablePlan:
    """CompiledRunPlan + the v2 graph spec lifted from the resolved bundle.

    ADR-0221 P3: the runtime kernel no longer rebuilds an executable
    plan via v0 ``GraphAssembler``. Instead, the kernel reads the v2
    graph (``nodes``/``edges``) straight from the bundle yaml. This
    wrapper carries that spec alongside the immutable compiled plan so
    ``DeclarativeRuntimeDriver`` can hand the graph to
    ``PlanInterpreter`` directly.
    """

    inner: object  # CompiledRunPlan — typed loosely to avoid cycle import.
    graph_spec: dict = field(default_factory=dict)
    profile_path: str = ""


def _wrap_v2_plan(plan, *, resolved):
    """Read the v2 graph spec from the resolved bundle yaml.

    Falls back to an empty graph when no bundle carries ``nodes``/
    ``edges`` — the interpreter will terminate immediately, which is
    the desired fail-loud signal for a missing bundle.
    """

    graph_spec = {"id": resolved.profile_path, "nodes": [], "edges": []}
    bundles = getattr(resolved, "bundles", ()) or ()
    for entry in bundles:
        if not isinstance(entry, str):
            continue
        path = Path(entry)
        if not path.exists():
            profile = Path(resolved.profile_path or ".")
            candidate = profile.parent / entry
            if candidate.exists():
                path = candidate
            else:
                continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not (isinstance(data, dict) and ("nodes" in data or "edges" in data)):
            continue
        # ADR-0221 P3 + outer-plan cutover: a phase subgraph bundle has
        # ``id: <phase>.subgraph`` and is meant to be entered through a
        # ``sub_spec_ref`` on the outer plan node, not executed as the
        # outer plan itself. Skip any bundle whose id ends in
        # ``.subgraph`` so the outer plan (``id`` not ending in
        # ``.subgraph``) is selected as the v2 graph spec.
        bundle_id = str(data.get("id", ""))
        if bundle_id.endswith(".subgraph"):
            continue
        graph_spec = data
        break
    # ADR-0221 P3: when no node carries ``entry: true``, mark the first
    # node as the entry so the v2 traversal has a starting point.
    nodes = graph_spec.get("nodes") or []
    if nodes and not any(node.get("entry") for node in nodes if isinstance(node, dict)):
        nodes[0]["entry"] = True
        graph_spec["nodes"] = nodes
    return V2ExecutablePlan(
        inner=plan,
        graph_spec=graph_spec,
        profile_path=resolved.profile_path,
    )


@dataclass(frozen=True, slots=True)
class CompileOptions:
    """PlanCompiler 的已验证编译输入（v2 — phase 字段已 no-op）。"""

    lifecycle: Scope = Scope.RUN
    visibility: tuple[Scope, ...] = ()
    acl_grants: tuple[str, ...] = ()
    budget_ceiling: BudgetCeiling | None = None
    task_id: str | None = None
    env_fingerprint: str | None = None
    include_disabled: bool = False
    # ADR-0221 P3: ``require_executable_phase_graph`` is ignored. The v2
    # plan does not carry a declarative phase graph; runtime builds the
    # executable plan from NodeExecutor subgraphs at boot.
    require_executable_phase_graph: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.lifecycle, Scope):
            raise TypeError("lifecycle must be a Scope")
        if not isinstance(self.visibility, tuple) or any(
            not isinstance(scope, Scope) for scope in self.visibility
        ):
            raise TypeError("visibility must be a tuple of Scope values")
        if not isinstance(self.acl_grants, tuple) or any(
            not isinstance(grant, str) or not grant.strip() for grant in self.acl_grants
        ):
            raise TypeError("acl_grants must be a tuple of non-empty strings")
        if self.budget_ceiling is not None and not isinstance(self.budget_ceiling, BudgetCeiling):
            raise TypeError("budget_ceiling must be a BudgetCeiling or None")
        for _field, value in (
            ("task_id", self.task_id),
            ("env_fingerprint", self.env_fingerprint),
        ):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field} must be a string or None")
        if not isinstance(self.include_disabled, bool):
            raise TypeError("include_disabled must be a boolean")
        if not isinstance(self.require_executable_phase_graph, bool):
            raise TypeError("require_executable_phase_graph must be a boolean")


def compile_plan(
    resolved: ResolvedProfile,
    *,
    options: CompileOptions | None = None,
) -> CompiledRunPlan:
    """Compile ``ResolvedProfile`` into an immutable ``CompiledRunPlan``.

    v2 shape: ``phase_graph`` is always ``None`` and ``phase_bindings``
    is always empty. Callers that need the executable graph ask
    ``PlanInterpreter`` for it at boot.
    """
    opts = options or CompileOptions()
    cap_options = CapabilityPlanOptions(include_disabled=opts.include_disabled)
    capability = project_capability_plan(resolved, options=cap_options)
    scope = ScopePlan(
        profile_path=resolved.profile_path,
        lifecycle=opts.lifecycle,
        visibility=opts.visibility,
        acl_grants=opts.acl_grants,
        budget_ceiling=opts.budget_ceiling or BudgetCeiling(),
    )
    return _wrap_v2_plan(
        CompiledRunPlan(
            profile_path=resolved.profile_path,
            capability=capability,
            scope=scope,
            plan_version=COMPILED_RUN_PLAN_VERSION,
            revision="v2",
            plugin_specs=(),  # ADR-0221 P3: PluginSpec projection lives in plugin_id index, not here.
            capability_bindings=capability.provider_bindings,
            # v2 ADR-0221 P3: phase_graph + phase_bindings retired from
            # CompiledRunPlan; runtime builds the executable plan via
            # PlanInterpreter + NodeExecutor subgraphs at boot.
            action_authority=ActionAuthorityPlan(),
        ),
        resolved=resolved,
    )


__all__ = [
    "COMPILED_RUN_PLAN_VERSION",
    "CompileOptions",
    "CompiledRunPlan",
    "PlanCompilerError",
    "compile_plan",
]
