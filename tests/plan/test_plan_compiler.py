"""Tests for CompiledRunPlan + PlanCompiler (ADR-0068 §一 + ADR-0074 PR-3).

This test covers:

- BudgetCeiling / ScopePlan (PR-3 最小版)
- CompiledRunPlan dataclass + plan_ref / capability_sub_plan_hash /
  control_sub_plan_hash / scope_sub_plan_hash
- PlanCompiler: compile_plan() from ResolvedProfile
- build_input_provenance: profile / bundle / patch / task / env
- compiled_run_plan_to_dict: JSON friendly output
- explain_compile_plan: lca-ops plan inspect minimal version
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.capability_plan import (
    CapabilityPlan,
    capability_plan_hash,
)
from lca.contracts.protocols.control_plan import (
    compute_control_plan_hash,
)
from lca.contracts.protocols.plan import (
    COMPILED_RUN_PLAN_VERSION,
    CompiledRunPlan,
    build_input_provenance,
    capability_sub_plan_hash,
    compiled_run_plan_ref,
    compiled_run_plan_to_dict,
    control_sub_plan_hash,
    scope_sub_plan_hash,
)
from lca.contracts.protocols.scope_plan import (
    BudgetCeiling,
    ScopePlan,
    scope_plan_hash,
)
from lca.harness.profile.plan_compiler import (
    CompileOptions,
    compile_plan,
    explain_compile_plan,
)
from lca.harness.profile.resolve import resolve_profile

# ── build_input_provenance ──────────────────────────────────────────


class TestBuildInputProvenance:
    def test_profile_only(self) -> None:
        prov = build_input_provenance("x.yaml", bundles=())
        assert prov == (("profile", "x.yaml"),)

    def test_profile_plus_bundles(self) -> None:
        prov = build_input_provenance("x.yaml", bundles=("a.yaml", "b.yaml"))
        assert prov == (
            ("profile", "x.yaml"),
            ("bundle", "a.yaml"),
            ("bundle", "b.yaml"),
        )

    def test_with_task_and_env(self) -> None:
        prov = build_input_provenance(
            "x.yaml",
            bundles=("a.yaml",),
            patches=("p.yaml",),
            task_id="task-123",
            env_fingerprint="env-v1",
        )
        assert prov == (
            ("profile", "x.yaml"),
            ("bundle", "a.yaml"),
            ("patch", "p.yaml"),
            ("task", "task-123"),
            ("env", "env-v1"),
        )


# ── CompiledRunPlan ─────────────────────────────────────────────────


class TestCompiledRunPlan:
    def test_minimal(self) -> None:
        # Build minimal sub-plans via resolvers
        resolved = resolve_profile("profiles/web-standard.yaml")
        from lca.harness.profile.capability_plan_resolver import (
            project_capability_plan,
        )
        from lca.harness.profile.control_plan_resolver import (
            project_control_plan,
        )

        capability = project_capability_plan(resolved)
        control = project_control_plan(resolved)
        scope = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(Scope.RUN,),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        plan = CompiledRunPlan(
            profile_path="x.yaml",
            capability=capability,
            control=control,
            scope=scope,
        )
        assert plan.profile_path == "x.yaml"
        assert plan.plan_version == COMPILED_RUN_PLAN_VERSION
        assert plan.revision == "v1"
        assert compiled_run_plan_ref(plan) == compiled_run_plan_ref(plan)

    def test_blank_profile_rejected(self) -> None:
        # Direct construction with empty profile_path
        from lca.harness.profile.capability_plan_resolver import (
            project_capability_plan,
        )
        from lca.harness.profile.control_plan_resolver import (
            project_control_plan,
        )

        resolved = resolve_profile("profiles/web-standard.yaml")
        capability = project_capability_plan(resolved)
        control = project_control_plan(resolved)
        scope = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        with pytest.raises(ValueError, match="profile_path must be non-empty"):
            CompiledRunPlan(
                profile_path="",
                capability=capability,
                control=control,
                scope=scope,
            )

    def test_input_provenance_normalized(self) -> None:
        # Non-tuple provenance item → ValueError
        from lca.harness.profile.capability_plan_resolver import (
            project_capability_plan,
        )
        from lca.harness.profile.control_plan_resolver import (
            project_control_plan,
        )

        resolved = resolve_profile("profiles/web-standard.yaml")
        capability = project_capability_plan(resolved)
        control = project_control_plan(resolved)
        scope = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        with pytest.raises(ValueError, match="must be \\(kind, path\\) tuple"):
            CompiledRunPlan(
                profile_path="x.yaml",
                capability=capability,
                control=control,
                scope=scope,
                input_provenance=("not_a_tuple",),  # type: ignore[arg-type]
            )

    def test_sub_plan_hashes(self) -> None:
        from lca.harness.profile.capability_plan_resolver import (
            project_capability_plan,
        )
        from lca.harness.profile.control_plan_resolver import (
            project_control_plan,
        )

        resolved = resolve_profile("profiles/web-standard.yaml")
        capability = project_capability_plan(resolved)
        control = project_control_plan(resolved)
        scope = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        plan = CompiledRunPlan(
            profile_path="x.yaml",
            capability=capability,
            control=control,
            scope=scope,
        )
        assert capability_sub_plan_hash(plan) == capability_plan_hash(capability)
        assert control_sub_plan_hash(plan) == compute_control_plan_hash(
            control.entries, control.profile_path
        )
        assert scope_sub_plan_hash(plan) == scope_plan_hash(scope)


class TestCompiledRunPlanHash:
    def test_plan_ref_is_stable(self) -> None:
        from lca.harness.profile.capability_plan_resolver import (
            project_capability_plan,
        )
        from lca.harness.profile.control_plan_resolver import (
            project_control_plan,
        )

        resolved = resolve_profile("profiles/web-standard.yaml")
        capability = project_capability_plan(resolved)
        control = project_control_plan(resolved)
        scope = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        plan = CompiledRunPlan(
            profile_path="x.yaml",
            capability=capability,
            control=control,
            scope=scope,
        )
        # Same plan → same plan_ref (twice)
        assert compiled_run_plan_ref(plan) == compiled_run_plan_ref(plan)
        assert compiled_run_plan_ref(plan) == compiled_run_plan_ref(plan)
        assert len(compiled_run_plan_ref(plan)) == 16

    def test_different_capability_yields_different_plan_ref(self) -> None:
        """不同 revision / 不同 profile_path → 不同 plan_ref。"""
        from lca.harness.profile.capability_plan_resolver import (
            project_capability_plan,
        )
        from lca.harness.profile.control_plan_resolver import (
            project_control_plan,
        )

        resolved = resolve_profile("profiles/web-standard.yaml")
        capability1 = project_capability_plan(resolved)
        capability2 = CapabilityPlan(
            profile_path="x.yaml",
            provider_bindings=capability1.provider_bindings,
            relations=capability1.relations,
            revision="v2",  # different revision → different capability hash
        )
        control = project_control_plan(resolved)
        scope = ScopePlan(
            profile_path="x.yaml",
            lifecycle=Scope.RUN,
            visibility=(),
            acl_grants=(),
            budget_ceiling=BudgetCeiling(),
        )
        plan1 = CompiledRunPlan(
            profile_path="x.yaml",
            capability=capability1,
            control=control,
            scope=scope,
        )
        plan2 = CompiledRunPlan(
            profile_path="x.yaml",
            capability=capability2,
            control=control,
            scope=scope,
        )
        # Different capability revision → different plan_ref
        assert compiled_run_plan_ref(plan1) != compiled_run_plan_ref(plan2)


class TestCompiledRunPlanToDict:
    def test_to_dict_round_trip(self) -> None:
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = compile_plan(resolved)
        d = compiled_run_plan_to_dict(plan)
        assert d["profile_path"] == plan.profile_path
        assert d["plan_version"] == COMPILED_RUN_PLAN_VERSION
        assert d["plan_ref"] == compiled_run_plan_ref(plan)
        assert d["revision"] == plan.revision
        assert "capability" in d
        assert "control" in d
        assert "scope" in d
        # sub_plan hashes
        assert d["capability"]["plan_hash"] == capability_sub_plan_hash(plan)
        assert d["control"]["plan_hash"] == control_sub_plan_hash(plan)
        assert d["scope"]["plan_hash"] == scope_sub_plan_hash(plan)


# ── PlanCompiler ────────────────────────────────────────────────────


class TestCompilePlan:
    def test_default_compile_web_standard(self) -> None:
        """PR-3 默认编译：web-standard.yaml → CompiledRunPlan with
        3 sub-plans populated.
        """
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = compile_plan(resolved)
        assert plan.profile_path == "profiles/web-standard.yaml"
        assert plan.plan_version == COMPILED_RUN_PLAN_VERSION
        # 3 sub-plans have non-empty content
        assert len(plan.capability.provider_bindings) >= 30
        assert len(plan.control.entries) == 12  # 3 concrete + 9 default no-op contributions
        assert len(plan.control.by_slot) == 11
        assert plan.scope.lifecycle is Scope.RUN
        assert len(plan.scope.visibility) == 8  # all Scope items

    def test_compile_with_custom_options(self) -> None:
        """CompileOptions 控制 lifecycle / visibility / acl / budget。"""
        resolved = resolve_profile("profiles/web-standard.yaml")
        opts = CompileOptions(
            lifecycle=Scope.AGENT,
            visibility=(Scope.AGENT, Scope.RUN),
            acl_grants=("cap.memory", "cap.tools"),
            budget_ceiling=BudgetCeiling(max_steps=50),
            task_id="task-abc",
        )
        plan = compile_plan(resolved, options=opts)
        assert plan.scope.lifecycle is Scope.AGENT
        assert plan.scope.visibility == (Scope.AGENT, Scope.RUN)
        assert plan.scope.acl_grants == ("cap.memory", "cap.tools")
        assert plan.scope.budget_ceiling.max_steps == 50
        assert ("task", "task-abc") in plan.input_provenance

    def test_include_disabled_changes_capability(self) -> None:
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan_default = compile_plan(resolved)
        plan_with_disabled = compile_plan(resolved, options=CompileOptions(include_disabled=True))
        # Including disabled plugins → more provider_bindings
        assert len(plan_with_disabled.capability.provider_bindings) >= len(
            plan_default.capability.provider_bindings
        )

    def test_plan_ref_changes_with_options(self) -> None:
        """input_provenance 含 task_id → 不同 plan_ref。"""
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan1 = compile_plan(resolved, options=CompileOptions(task_id="t1"))
        plan2 = compile_plan(resolved, options=CompileOptions(task_id="t2"))
        assert compiled_run_plan_ref(plan1) != compiled_run_plan_ref(plan2)


class TestExplainCompilePlan:
    def test_explain_default(self) -> None:
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = compile_plan(resolved)
        info = explain_compile_plan(plan)
        assert info["profile_path"] == "profiles/web-standard.yaml"
        assert info["plan_ref"] == compiled_run_plan_ref(plan)
        assert info["plan_version"] == COMPILED_RUN_PLAN_VERSION
        # sub_plans
        assert info["sub_plans"]["capability"]["binding_count"] >= 30
        assert info["sub_plans"]["control"]["entry_count"] == 12
        assert len(info["sub_plans"]["control"]["covered_slots"]) == 11
        assert "stop.decide" in info["sub_plans"]["control"]["covered_slots"]
        assert "think.guard" in info["sub_plans"]["control"]["covered_slots"]
        assert info["sub_plans"]["scope"]["lifecycle"] == "run"
        assert len(info["sub_plans"]["scope"]["visibility"]) == 8
