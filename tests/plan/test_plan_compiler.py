"""Tests for ``CompiledRunPlan`` and the declarative plan compiler.

The control surface is asserted through typed ``control_entries`` projected from
native ``PluginSpec.contributes``. No legacy ``ControlPlan`` participates in a
compiled runtime plan.
"""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.capability_plan import (
    CapabilityPlan,
    capability_plan_hash,
)
from lca.contracts.protocols.plan import COMPILED_RUN_PLAN_VERSION, CompiledRunPlan
from lca.contracts.protocols.scope_plan import (
    BudgetCeiling,
    ScopePlan,
    scope_plan_hash,
)
from lca.harness.plan import (
    build_input_provenance,
    capability_sub_plan_hash,
    compiled_run_plan_ref,
    compiled_run_plan_to_dict,
    control_entries_sub_plan_hash,
    declarative_plan_hash,
    scope_sub_plan_hash,
)
from lca.harness.profile.plan_compiler import (
    CompileOptions,
    compile_plan,
    explain_compile_plan,
)
from lca.harness.profile.resolve import ResolvedProfile, resolve_profile
from lca.layer0_infra.ops.commands.declarative import render_declarative_graph

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


class TestCompiledPlanPatchProvenance:
    def test_patched_resolved_plugin_contributes_to_plan_provenance(self) -> None:
        resolved = resolve_profile("profiles/web-standard.yaml")
        patched_plugin = replace(
            resolved.plugins[0],
            source=f"{resolved.plugins[0].source}+patch",
        )
        patched = replace(
            resolved,
            plugins=(patched_plugin, *resolved.plugins[1:]),
        )

        original_plan = compile_plan(resolved)
        patched_plan = compile_plan(patched)

        assert (
            "patch",
            f"{patched.profile_path}#patch.{patched_plugin.id}",
        ) in patched_plan.input_provenance
        assert compiled_run_plan_ref(patched_plan) == compiled_run_plan_ref(compile_plan(patched))
        assert compiled_run_plan_ref(patched_plan) != compiled_run_plan_ref(original_plan)


# ── CompiledRunPlan ─────────────────────────────────────────────────


def _minimal_plan_inputs() -> tuple[CapabilityPlan, ScopePlan]:
    resolved = resolve_profile("profiles/web-standard.yaml")
    from lca.harness.profile.capability_plan_resolver import project_capability_plan

    capability = project_capability_plan(resolved)
    scope = ScopePlan(
        profile_path="x.yaml",
        lifecycle=Scope.RUN,
        visibility=(Scope.RUN,),
        acl_grants=(),
        budget_ceiling=BudgetCeiling(),
    )
    return capability, scope


class TestCompiledRunPlan:
    def test_minimal(self) -> None:
        capability, scope = _minimal_plan_inputs()

        plan = CompiledRunPlan(
            profile_path="x.yaml",
            capability=capability,
            scope=scope,
        )
        assert plan.profile_path == "x.yaml"
        assert plan.plan_version == COMPILED_RUN_PLAN_VERSION
        assert plan.revision == "v2"
        assert plan.control_entries == ()
        assert compiled_run_plan_ref(plan) == compiled_run_plan_ref(plan)

    def test_blank_profile_rejected(self) -> None:
        capability, scope = _minimal_plan_inputs()

        with pytest.raises(ValueError, match="profile_path must be non-empty"):
            CompiledRunPlan(
                profile_path="",
                capability=capability,
                scope=scope,
            )

    def test_input_provenance_normalized(self) -> None:
        capability, scope = _minimal_plan_inputs()

        with pytest.raises(ValueError, match="must be \\(kind, path\\) tuple"):
            CompiledRunPlan(
                profile_path="x.yaml",
                capability=capability,
                scope=scope,
                input_provenance=("not_a_tuple",),
            )

    def test_sub_plan_hashes(self) -> None:
        capability, scope = _minimal_plan_inputs()
        plan = CompiledRunPlan(
            profile_path="x.yaml",
            capability=capability,
            scope=scope,
        )
        assert capability_sub_plan_hash(plan) == capability_plan_hash(capability)
        assert control_entries_sub_plan_hash(plan) == declarative_plan_hash(
            {"profile_path": "x.yaml", "control_entries": ()}
        )
        assert scope_sub_plan_hash(plan) == scope_plan_hash(scope)


class TestCompiledRunPlanHash:
    def test_plan_ref_is_stable(self) -> None:
        capability, scope = _minimal_plan_inputs()
        plan = CompiledRunPlan(
            profile_path="x.yaml",
            capability=capability,
            scope=scope,
        )
        assert compiled_run_plan_ref(plan) == compiled_run_plan_ref(plan)
        assert len(compiled_run_plan_ref(plan)) == 16

    def test_different_capability_yields_different_plan_ref(self) -> None:
        """不同 revision / 不同 profile_path → 不同 plan_ref。"""
        capability1, scope = _minimal_plan_inputs()
        capability2 = CapabilityPlan(
            profile_path="x.yaml",
            provider_bindings=capability1.provider_bindings,
            relations=capability1.relations,
            revision="v2",
        )
        plan1 = CompiledRunPlan(
            profile_path="x.yaml",
            capability=capability1,
            scope=scope,
        )
        plan2 = CompiledRunPlan(
            profile_path="x.yaml",
            capability=capability2,
            scope=scope,
        )
        assert compiled_run_plan_ref(plan1) != compiled_run_plan_ref(plan2)


class TestCompiledRunPlanToDict:
    def test_to_dict_round_trip(self) -> None:
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = compile_plan(resolved)
        data = compiled_run_plan_to_dict(plan)
        assert data["profile_path"] == plan.profile_path
        assert data["plan_version"] == COMPILED_RUN_PLAN_VERSION
        assert data["plan_ref"] == compiled_run_plan_ref(plan)
        assert data["revision"] == "v3"
        assert "capability" in data
        assert "control" in data
        assert "scope" in data
        assert data["capability"]["plan_hash"] == capability_sub_plan_hash(plan)
        assert data["control"]["plan_hash"] == control_entries_sub_plan_hash(plan)
        assert data["scope"]["plan_hash"] == scope_sub_plan_hash(plan)


# ── PlanCompiler ────────────────────────────────────────────────────


class TestCompilePlan:
    def test_default_compile_web_standard(self) -> None:
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = compile_plan(resolved)
        assert plan.profile_path == "profiles/web-standard.yaml"
        assert plan.plan_version == COMPILED_RUN_PLAN_VERSION
        assert len(plan.capability.provider_bindings) >= 30
        assert len(plan.control_entries) == 12
        assert {entry.phase.value for entry in plan.control_entries} == {
            "perceive",
            "think",
            "act",
            "remember",
            "stop",
        }
        assert plan.scope.lifecycle is Scope.RUN
        assert len(plan.scope.visibility) == 8

    def test_compile_with_custom_options(self) -> None:
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
        assert len(plan_with_disabled.capability.provider_bindings) >= len(
            plan_default.capability.provider_bindings
        )

    def test_capability_subplan_uses_native_spec_catalog_as_the_only_source(self) -> None:
        """每一份运行能力事实必须从同一原生 PluginSpec 目录导出。"""
        from lca.harness.plugin_api import PluginDefinition

        resolved = resolve_profile("profiles/web-standard.yaml")
        source = next(
            plugin
            for plugin in resolved.plugins
            if not plugin.disabled and plugin.definition.spec.provides
        )
        native_only_capability = "native.catalog_capability"
        declared = source.definition.spec.provides[0]
        mutated_spec = replace(
            source.definition.spec,
            provides=(
                *source.definition.spec.provides,
                replace(
                    declared,
                    key=native_only_capability,
                    resolution_key=native_only_capability,
                ),
            ),
        )
        mutated = replace(
            resolved,
            plugins=(
                replace(source, definition=replace(source.definition, spec=mutated_spec)),
                *(plugin for plugin in resolved.plugins if plugin.id != source.id),
            ),
        )

        plan = compile_plan(mutated)
        provider_bindings = {
            binding.capability: binding for binding in plan.capability.provider_bindings
        }

        assert "provides" not in {field.name for field in fields(PluginDefinition)}
        assert native_only_capability in provider_bindings
        assert provider_bindings[declared.key].owner_plugin == source.id
        assert provider_bindings[declared.key].resolution_key == declared.resolution_key
        assert provider_bindings[declared.key].revision == source.definition.spec.revision

    def test_compilation_projections_reuse_active_view_by_default(self) -> None:
        from lca.harness.profile.projection import ProfileCompilationProjections

        resolved = resolve_profile("profiles/web-standard.yaml")
        projections = ProfileCompilationProjections.build(resolved)

        assert projections.active is projections.selected
        assert projections.active.resolved is resolved
        assert projections.active.include_disabled is False

    def test_compilation_projections_isolate_inspection_view(self) -> None:
        from lca.harness.profile.projection import ProfileCompilationProjections

        resolved = resolve_profile("profiles/web-standard.yaml")
        projections = ProfileCompilationProjections.build(resolved, include_disabled=True)

        assert projections.active is not projections.selected
        assert projections.active.resolved is resolved
        assert projections.selected.resolved is resolved
        assert projections.active.include_disabled is False
        assert projections.selected.include_disabled is True

    def test_compile_reuses_one_profile_projection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from lca.harness.profile.projection import ResolvedProfileProjection

        resolved = resolve_profile("profiles/web-standard.yaml")
        original_build = ResolvedProfileProjection.build
        builds = 0

        def tracked_build(
            cls: type[ResolvedProfileProjection],
            value: ResolvedProfile,
            *,
            include_disabled: bool = False,
        ) -> ResolvedProfileProjection:
            nonlocal builds
            builds += 1
            assert value is resolved
            return original_build(value, include_disabled=include_disabled)

        monkeypatch.setattr(
            ResolvedProfileProjection,
            "build",
            classmethod(tracked_build),
        )

        compile_plan(resolved)

        assert builds == 1

    def test_projection_reuse_rejects_a_different_resolved_profile(self) -> None:
        from lca.harness.profile.capability_plan_resolver import project_capability_plan
        from lca.harness.profile.projection import ResolvedProfileProjection

        projection = ResolvedProfileProjection.build(resolve_profile("profiles/web-standard.yaml"))
        other_resolved = resolve_profile("profiles/web-standard.yaml")

        with pytest.raises(ValueError, match="different resolved profile"):
            project_capability_plan(other_resolved, projection=projection)

    def test_plan_ref_changes_with_options(self) -> None:
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
        assert info["sub_plans"]["capability"]["binding_count"] >= 30
        assert info["sub_plans"]["control"]["entry_count"] == 12
        assert info["sub_plans"]["control"]["covered_phases"] == [
            "act",
            "perceive",
            "remember",
            "stop",
            "think",
        ]
        assert info["sub_plans"]["scope"]["lifecycle"] == "run"
        assert len(info["sub_plans"]["scope"]["visibility"]) == 8

    def test_explain_contains_complete_declarative_graph_projection(self) -> None:
        plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
        info = explain_compile_plan(plan)["declarative"]

        graph = info["phase_graph"]
        assert graph["entry"] == "perceive.main"
        assert {node["semantic_phase"] for node in graph["nodes"]} == {
            "perceive",
            "think",
            "act",
            "reflect",
            "remember",
            "stop",
        }
        assert any(
            edge["source"] == "stop.main"
            and edge["target"] == "perceive.main"
            and edge["loop"]["max_iterations"] == 8
            for edge in graph["edges"]
        )
        assert all(
            {"capability", "provider", "cardinality", "scope", "grant", "provenance"}
            <= set(binding)
            for binding in info["capability_bindings"]
        )
        assert all(
            {"source", "type", "target", "mode"} <= set(relation) for relation in info["relations"]
        )
        assert info["provenance"]["profile_path"] == "profiles/web-standard.yaml"
        assert {"allowed_effects", "approval_required", "idempotency_required"} <= set(
            info["effect_policy"]
        )

    def test_render_graph_contains_phase_capability_and_relation_edges(self) -> None:
        graph = render_declarative_graph(Path("profiles/web-standard.yaml"))

        assert graph.startswith("flowchart LR")
        assert "subgraph phase_graph" in graph
        assert "subgraph capability_graph" in graph
        assert "subgraph relation_graph" in graph
        assert "phase_perceive_main" in graph
        assert "phase_stop_main" in graph
        assert "provides" in graph
        assert "loop" in graph
