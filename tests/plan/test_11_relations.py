"""Tests for 11 relations algebra (ADR-0069 §三 + ADR-0074 PR-2.5).

This test covers:

- Relation enum: 11 members + canonical values + parse + validate_iterable
- TypedRelation dataclass: source/target/kind/evidence/scope/weight
  + module-level accessors (typed_relation_to_dict /
  typed_relations_from_iter)
- CapabilityPlan: provider_bindings + relations + plan_hash + 3
  module-level accessors
- CapabilityPlanResolver: project from ResolvedProfile, validate
  targets, accept description-prefixed targets (descriptor:/fact:/journal.)
- End-to-end: web-standard.yaml projection → 42 bindings + 0 explicit
  relations
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from lca.contracts.atoms.relation import (
    NEW_RELATIONS,
    RELATION_GROUP_HINT,
    Relation,
    all_relation_values,
    parse_relation,
    validate_relations,
)
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.relation import (
    TypedRelation,
    typed_relation_to_dict,
    typed_relations_from_iter,
)
from lca.contracts.protocols.perceive.capability_plan import (
    CapabilityPlan,
    ProviderBinding,
    capability_plan_hash,
    capability_plan_to_dict,
    relations_from_plugin,
    relations_of_kind,
    relations_to_plugin,
)
from lca.harness.profile.capability_plan_resolver import (
    CapabilityPlanOptions,
    CapabilityPlanResolveError,
    project_capability_plan,
)
from lca.harness.profile.resolve import resolve_profile

# ── Relation enum ────────────────────────────────────────────────────


class TestRelationEnum:
    def test_has_exactly_eleven_members(self) -> None:
        members = list(Relation)
        assert len(members) == 11

    def test_canonical_values(self) -> None:
        """5 老 + 6 新；字符串值稳定（序列化 / plan_ref 引用）。"""
        assert Relation.PROVIDES.value == "provides"
        assert Relation.REQUIRES.value == "requires"
        assert Relation.CONTRIBUTES_TO.value == "contributes_to"
        assert Relation.READS_FACT.value == "reads_fact"
        assert Relation.EMITS_FACT.value == "emits_fact"
        # 6 新关系
        assert Relation.GOVERNS.value == "governs"
        assert Relation.EXECUTES.value == "executes"
        assert Relation.DELEGATES.value == "delegates"
        assert Relation.PROJECTS.value == "projects"
        assert Relation.REVISES.value == "revises"
        assert Relation.EVALUATES.value == "evaluates"

    def test_str_enum_value_equality(self) -> None:
        assert Relation.GOVERNS == "governs"

    def test_no_duplicate_values(self) -> None:
        values = [r.value for r in Relation]
        assert len(values) == len(set(values))

    def test_all_relation_values_returns_all(self) -> None:
        values = all_relation_values()
        assert len(values) == 11
        assert "governs" in values
        assert "evaluates" in values


class TestNewRelationsSplit:
    """6 新关系集合 NEW_RELATIONS（PR-2.5 落地）。"""

    def test_new_relations_size(self) -> None:
        assert len(NEW_RELATIONS) == 6

    def test_new_relations_set(self) -> None:
        assert (
            frozenset(
                {
                    Relation.GOVERNS,
                    Relation.EXECUTES,
                    Relation.DELEGATES,
                    Relation.PROJECTS,
                    Relation.REVISES,
                    Relation.EVALUATES,
                }
            )
            == NEW_RELATIONS
        )

    def test_relation_group_hint_covers_all(self) -> None:
        """每个 Relation 在 RELATION_GROUP_HINT 有群提示（PR-12 图谱用）。"""
        for r in Relation:
            assert r in RELATION_GROUP_HINT


class TestParseRelation:
    def test_round_trip_string(self) -> None:
        for r in Relation:
            assert parse_relation(r.value) is r

    def test_round_trip_enum(self) -> None:
        for r in Relation:
            assert parse_relation(r) is r

    def test_unknown_string_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown relation"):
            parse_relation("depends_on")

    def test_non_string_raises(self) -> None:
        with pytest.raises(TypeError):
            parse_relation(42)


class TestValidateRelations:
    def test_valid_list(self) -> None:
        result = validate_relations(["governs", "executes", "delegates"])
        assert result == (
            Relation.GOVERNS,
            Relation.EXECUTES,
            Relation.DELEGATES,
        )

    def test_valid_tuple(self) -> None:
        result = validate_relations(("projects",))
        assert result == (Relation.PROJECTS,)

    def test_empty_returns_empty(self) -> None:
        assert validate_relations([]) == ()

    def test_unknown_member_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown relation"):
            validate_relations(["governs", "calls"])

    def test_non_iterable_raises(self) -> None:
        with pytest.raises(ValueError, match="must be list/tuple"):
            validate_relations("governs")


# ── TypedRelation dataclass ──────────────────────────────────────────


class TestTypedRelationConstruction:
    def test_minimal_valid(self) -> None:
        rel = TypedRelation(source="plugin.a", target="plugin.b", kind=Relation.GOVERNS)
        assert rel.source == "plugin.a"
        assert rel.target == "plugin.b"
        assert rel.kind is Relation.GOVERNS
        assert rel.evidence == ()
        assert rel.scope is None
        assert rel.weight == 1.0

    def test_full(self) -> None:
        rel = TypedRelation(
            source="plugin.a",
            target="descriptor:policy.gate.denied",
            kind=Relation.EMITS_FACT,
            evidence=("policy.gate.denied",),
            scope=Scope.RUN,
            weight=0.8,
        )
        assert rel.evidence == ("policy.gate.denied",)
        assert rel.scope is Scope.RUN
        assert rel.weight == 0.8

    def test_blank_source_rejected(self) -> None:
        with pytest.raises(ValueError, match="source must be non-empty"):
            TypedRelation(source="", target="plugin.b", kind=Relation.GOVERNS)

    def test_blank_target_rejected(self) -> None:
        with pytest.raises(ValueError, match="target must be non-empty"):
            TypedRelation(source="plugin.a", target="", kind=Relation.GOVERNS)

    def test_negative_weight_rejected(self) -> None:
        with pytest.raises(ValueError, match="weight must be >= 0"):
            TypedRelation(
                source="plugin.a",
                target="plugin.b",
                kind=Relation.GOVERNS,
                weight=-1.0,
            )

    def test_str_kind_normalized(self) -> None:
        rel = TypedRelation(source="a", target="b", kind="executes")
        assert rel.kind is Relation.EXECUTES


class TestTypedRelationAccessors:
    def test_typed_relation_to_dict(self) -> None:
        rel = TypedRelation(
            source="plugin.a",
            target="plugin.b",
            kind=Relation.GOVERNS,
            evidence=("policy.x",),
            scope=Scope.RUN,
        )
        d = typed_relation_to_dict(rel)
        assert d["source"] == "plugin.a"
        assert d["target"] == "plugin.b"
        assert d["kind"] == "governs"
        assert d["evidence"] == ["policy.x"]
        assert d["scope"] == "run"
        assert d["scope_canonical"] == "run"

    def test_invocation_scope_canonicalizes_to_turn(self) -> None:
        rel = TypedRelation(source="a", target="b", kind=Relation.GOVERNS, scope=Scope.INVOCATION)
        d = typed_relation_to_dict(rel)
        assert d["scope"] == "invocation"
        assert d["scope_canonical"] == "turn"

    def test_typed_relations_from_iter(self) -> None:
        relations = typed_relations_from_iter(
            [
                {"source": "a", "target": "b", "kind": "governs"},
                {"source": "b", "target": "c", "kind": "executes", "weight": 2.0},
            ]
        )
        assert len(relations) == 2
        assert relations[0].kind is Relation.GOVERNS
        assert relations[1].weight == 2.0

    def test_typed_relations_from_iter_accepts_objects(self) -> None:
        existing = TypedRelation(source="a", target="b", kind=Relation.GOVERNS)
        result = typed_relations_from_iter([existing])
        assert result == (existing,)

    def test_typed_relations_missing_fields_raises(self) -> None:
        with pytest.raises(ValueError, match="missing required field"):
            typed_relations_from_iter([{"source": "a", "target": "b"}])

    def test_typed_relations_unknown_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown relation"):
            typed_relations_from_iter([{"source": "a", "target": "b", "kind": "calls"}])

    def test_typed_relations_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="must be dict or TypedRelation"):
            typed_relations_from_iter(["just a string"])


# ── ProviderBinding / CapabilityPlan ────────────────────────────────


class TestProviderBinding:
    def test_minimal_valid(self) -> None:
        bp = ProviderBinding(capability="memory", owner_plugin="lca-memory-service")
        assert bp.capability == "memory"
        assert bp.owner_plugin == "lca-memory-service"
        assert bp.effect_class == "none"
        assert bp.revision == ""

    def test_with_effect_class(self) -> None:
        bp = ProviderBinding(
            capability="tools",
            owner_plugin="lca-tools-provider",
            effect_class="tools",
            revision="v2",
        )
        assert bp.effect_class == "tools"
        assert bp.revision == "v2"

    def test_blank_capability_rejected(self) -> None:
        with pytest.raises(ValueError, match="capability must be non-empty"):
            ProviderBinding(capability="", owner_plugin="plugin")

    def test_blank_owner_rejected(self) -> None:
        with pytest.raises(ValueError, match="owner_plugin must be non-empty"):
            ProviderBinding(capability="memory", owner_plugin="")


class TestCapabilityPlan:
    def test_minimal(self) -> None:
        plan = CapabilityPlan(
            profile_path="x.yaml",
            provider_bindings=(),
            relations=(),
        )
        assert plan.profile_path == "x.yaml"
        assert plan.provider_bindings == ()
        assert plan.relations == ()
        assert plan.revision == "v1"

    def test_blank_profile_rejected(self) -> None:
        with pytest.raises(ValueError, match="profile_path must be non-empty"):
            CapabilityPlan(profile_path="", provider_bindings=(), relations=())

    def test_bindings_must_be_tuple(self) -> None:
        with pytest.raises(ValueError, match="provider_bindings must be tuple"):
            CapabilityPlan(
                profile_path="x.yaml",
                provider_bindings=[],  # type: ignore[arg-type]
                relations=(),
            )

    def test_relations_must_be_tuple(self) -> None:
        with pytest.raises(ValueError, match="relations must be tuple"):
            CapabilityPlan(
                profile_path="x.yaml",
                provider_bindings=(),
                relations=[],  # type: ignore[arg-type]
            )


class TestCapabilityPlanHash:
    def test_empty_plan_hash_is_stable(self) -> None:
        plan = CapabilityPlan(profile_path="x.yaml", provider_bindings=(), relations=())
        h1 = capability_plan_hash(plan)
        h2 = capability_plan_hash(plan)
        assert h1 == h2
        assert len(h1) == 16

    def test_different_profile_yields_different_hash(self) -> None:
        plan1 = CapabilityPlan(profile_path="x.yaml", provider_bindings=(), relations=())
        plan2 = CapabilityPlan(profile_path="y.yaml", provider_bindings=(), relations=())
        assert capability_plan_hash(plan1) != capability_plan_hash(plan2)

    def test_order_invariance(self) -> None:
        """bindings / relations 顺序不影响 hash（sorted before hashing）。"""
        bp1 = ProviderBinding(capability="a", owner_plugin="p1")
        bp2 = ProviderBinding(capability="b", owner_plugin="p2")
        plan1 = CapabilityPlan(profile_path="x", provider_bindings=(bp1, bp2), relations=())
        plan2 = CapabilityPlan(profile_path="x", provider_bindings=(bp2, bp1), relations=())
        assert capability_plan_hash(plan1) == capability_plan_hash(plan2)

    def test_different_bindings_yield_different_hash(self) -> None:
        bp1 = ProviderBinding(capability="a", owner_plugin="p1")
        bp2 = ProviderBinding(capability="b", owner_plugin="p2")
        plan1 = CapabilityPlan(profile_path="x", provider_bindings=(bp1,), relations=())
        plan2 = CapabilityPlan(profile_path="x", provider_bindings=(bp2,), relations=())
        assert capability_plan_hash(plan1) != capability_plan_hash(plan2)

    @pytest.mark.parametrize(
        "metadata",
        [
            {"effect_class": "world"},
            {"revision": "v2"},
            {"required_in_production": True},
            {"fallback_policy": "test_default"},
            {"owner_kind": "contributor"},
            {"scope": "session"},
            {"provenance": "bundles/alternate.yaml"},
        ],
    )
    def test_binding_metadata_changes_yield_different_hash(
        self, metadata: dict[str, str | bool]
    ) -> None:
        """plan_ref 的 capability 子摘要必须覆盖每个 runtime binding 语义。"""
        baseline = ProviderBinding(capability="memory", owner_plugin="p1")
        changed = ProviderBinding(capability="memory", owner_plugin="p1", **metadata)
        plan = CapabilityPlan(profile_path="x", provider_bindings=(baseline,), relations=())
        changed_plan = CapabilityPlan(profile_path="x", provider_bindings=(changed,), relations=())

        assert capability_plan_hash(plan) != capability_plan_hash(changed_plan)


class TestCapabilityPlanAccessors:
    def test_relations_of_kind(self) -> None:
        r1 = TypedRelation(source="a", target="b", kind=Relation.GOVERNS)
        r2 = TypedRelation(source="b", target="c", kind=Relation.EXECUTES)
        r3 = TypedRelation(source="a", target="c", kind=Relation.GOVERNS)
        plan = CapabilityPlan(profile_path="x", provider_bindings=(), relations=(r1, r2, r3))
        assert relations_of_kind(plan, Relation.GOVERNS) == (r1, r3)
        assert relations_of_kind(plan, "executes") == (r2,)
        assert relations_of_kind(plan, Relation.DELEGATES) == ()

    def test_relations_from_plugin(self) -> None:
        r1 = TypedRelation(source="a", target="b", kind=Relation.GOVERNS)
        r2 = TypedRelation(source="b", target="c", kind=Relation.EXECUTES)
        r3 = TypedRelation(source="a", target="c", kind=Relation.DELEGATES)
        plan = CapabilityPlan(profile_path="x", provider_bindings=(), relations=(r1, r2, r3))
        assert relations_from_plugin(plan, "a") == (r1, r3)
        assert relations_from_plugin(plan, "b") == (r2,)

    def test_relations_to_plugin(self) -> None:
        r1 = TypedRelation(source="a", target="b", kind=Relation.GOVERNS)
        r2 = TypedRelation(source="b", target="c", kind=Relation.EXECUTES)
        plan = CapabilityPlan(profile_path="x", provider_bindings=(), relations=(r1, r2))
        assert relations_to_plugin(plan, "b") == (r1,)
        assert relations_to_plugin(plan, "c") == (r2,)

    def test_capability_plan_to_dict(self) -> None:
        bp = ProviderBinding(capability="memory", owner_plugin="lca-memory-service")
        rel = TypedRelation(source="a", target="b", kind=Relation.GOVERNS)
        plan = CapabilityPlan(
            profile_path="x",
            provider_bindings=(bp,),
            relations=(rel,),
        )
        d = capability_plan_to_dict(plan)
        assert d["profile_path"] == "x"
        assert d["revision"] == "v1"
        assert d["plan_hash"] == capability_plan_hash(plan)
        assert len(d["provider_bindings"]) == 1
        assert len(d["relations"]) == 1

    def test_capability_plan_to_dict_projects_complete_binding_metadata(self) -> None:
        binding = ProviderBinding(
            capability="memory",
            owner_plugin="lca-memory-service",
            effect_class="world",
            revision="v2",
            required_in_production=True,
            fallback_policy="test_default",
            owner_kind="contributor",
            scope="session",
            provenance="bundles/memory.yaml",
        )
        plan = CapabilityPlan(profile_path="x", provider_bindings=(binding,), relations=())

        payload = capability_plan_to_dict(plan)["provider_bindings"][0]

        assert payload == {
            "capability": "memory",
            "owner_plugin": "lca-memory-service",
            "resolution_key": "memory",
            "effect_class": "world",
            "revision": "v2",
            "required_in_production": True,
            "fallback_policy": "test_default",
            "owner_kind": "contributor",
            "scope": "session",
            "provenance": "bundles/memory.yaml",
        }

    def test_selector_binding_projects_its_registry_as_resolution_key(self) -> None:
        """The compiler owns selector syntax; runtime binding sees one seam key."""

        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = project_capability_plan(resolved)

        registry_binding = next(
            item
            for item in plan.provider_bindings
            if item.capability == "run_loop_driver_registry[cognitive]"
        )
        tool_binding = next(
            item
            for item in plan.provider_bindings
            if item.capability == "cordis_control_tool_factory"
        )

        assert registry_binding.resolution_key == "run_loop_driver_registry"
        assert tool_binding.resolution_key == "cordis_control_tool_factory"

        registry_spec = next(
            spec
            for spec in resolve_profile("profiles/web-standard.yaml").plugins
            if spec.id == registry_binding.owner_plugin
        ).definition.spec
        tool_spec = next(
            spec
            for spec in resolve_profile("profiles/web-standard.yaml").plugins
            if spec.id == tool_binding.owner_plugin
        ).definition.spec
        assert (
            next(
                capability
                for capability in registry_spec.provides
                if capability.key == registry_binding.capability
            ).resolution_key
            == registry_binding.resolution_key
        )
        assert (
            next(
                capability
                for capability in tool_spec.provides
                if capability.key == tool_binding.capability
            ).resolution_key
            == tool_binding.resolution_key
        )


# ── Resolver ─────────────────────────────────────────────────────────


class TestProjectCapabilityPlan:
    def test_web_standard_yields_bindings_no_relations(self) -> None:
        """web-standard.yaml 当前没有 plugin 声明 ``meta.relations``，
        所以 plan 含 42 个 provider_bindings (来自 provides) + 0 relations。
        """
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = project_capability_plan(resolved)
        # 42 plugins in web-standard; each contributes ≥ 1 capability
        assert len(plan.provider_bindings) >= 30
        # No explicit relations declared yet
        assert plan.relations == ()
        # Hash stable across runs
        plan_again = project_capability_plan(resolved)
        assert capability_plan_hash(plan) == capability_plan_hash(plan_again)

    def test_typed_definition_relations_take_precedence_over_compat_metadata(self) -> None:
        """正常声明路径不应重新泄漏到 setup.meta 的兼容读取。"""
        resolved = resolve_profile("profiles/web-standard.yaml")
        source = resolved.plugins[0]
        target = next(plugin for plugin in resolved.plugins if plugin.id != source.id)
        typed_source = replace(
            source,
            definition=replace(
                source.definition,
                relations=({"target": target.id, "kind": "governs"},),
            ),
        )
        typed_resolved = replace(
            resolved,
            plugins=(typed_source, *resolved.plugins[1:]),
        )
        original_meta = getattr(source.definition.setup, "meta", None)
        try:
            source.definition.setup.meta = {
                **(original_meta or {}),
                "relations": [{"target": target.id, "kind": "delegates"}],
            }
            plan = project_capability_plan(typed_resolved)
        finally:
            source.definition.setup.meta = original_meta

        declared = [relation for relation in plan.relations if relation.source == source.id]
        assert [(relation.target, relation.kind) for relation in declared] == [
            (target.id, Relation.GOVERNS)
        ]

    def test_provider_bindings_have_capability_owner(self) -> None:
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = project_capability_plan(resolved)
        # Sample: lca-llm-service provides 'llm'
        llm_bindings = [b for b in plan.provider_bindings if b.capability == "llm"]
        assert len(llm_bindings) == 1
        assert llm_bindings[0].owner_plugin == "lca-llm-service"

    def test_disabled_excluded_by_default(self) -> None:
        """include_disabled=False 时 disabled plugin 不参与。"""
        resolved = resolve_profile("profiles/web-standard.yaml")
        plan_default = project_capability_plan(resolved)
        plan_disabled = project_capability_plan(
            resolved, options=CapabilityPlanOptions(include_disabled=True)
        )
        # Including disabled may yield more bindings
        assert len(plan_disabled.provider_bindings) >= len(plan_default.provider_bindings)

    def test_validate_targets_rejects_unknown_source(self) -> None:
        """rel.source 指向不存在的 plugin id → CapabilityPlanResolveError."""
        # Fabricate a relation by patching a plugin's meta after resolution.
        resolved = resolve_profile("profiles/web-standard.yaml")
        plugin = next(iter(resolved.plugins))
        original_meta = getattr(plugin.definition.setup, "meta", None)
        try:
            # replace meta entirely (not merge) so unknown source is the only error.
            plugin.definition.setup.meta = {
                "id": plugin.id,
                "relations": [
                    {
                        "source": "nonexistent.plugin",
                        "target": "any.target",
                        "kind": "governs",
                    }
                ],
            }
            with pytest.raises(CapabilityPlanResolveError, match="not in known plugin"):
                project_capability_plan(resolved)
        finally:
            plugin.definition.setup.meta = original_meta

    def test_validate_targets_rejects_bad_target_for_fact_relation(self) -> None:
        """reads_fact / emits_fact 的 target 必须是 descriptor 风格。"""
        resolved = resolve_profile("profiles/web-standard.yaml")
        plugin = next(iter(resolved.plugins))
        original_meta = getattr(plugin.definition.setup, "meta", None)
        try:
            plugin.definition.setup.meta = {
                **(original_meta or {}),
                "relations": [{"target": "some-other-plugin", "kind": "reads_fact"}],
            }
            with pytest.raises(CapabilityPlanResolveError, match="fact descriptor"):
                project_capability_plan(resolved)
        finally:
            plugin.definition.setup.meta = original_meta

    def test_validate_targets_accepts_descriptor_prefix(self) -> None:
        """``descriptor:`` / ``fact:`` / ``journal.`` 前缀 target 合法。"""
        resolved = resolve_profile("profiles/web-standard.yaml")
        plugin = next(iter(resolved.plugins))
        original_meta = getattr(plugin.definition.setup, "meta", None)
        try:
            plugin.definition.setup.meta = {
                **(original_meta or {}),
                "relations": [
                    {"target": "descriptor:policy.gate.denied", "kind": "emits_fact"},
                    {"target": "fact:policy.x", "kind": "reads_fact"},
                    {"target": "journal.event_x", "kind": "evaluates"},
                ],
            }
            plan = project_capability_plan(resolved)
            # 3 relations added
            assert len(plan.relations) >= 3
        finally:
            plugin.definition.setup.meta = original_meta

    def test_validate_targets_accepts_other_plugin(self) -> None:
        """``target`` 指向另一 plugin id → 合法（governs / executes / etc.）。"""
        resolved = resolve_profile("profiles/web-standard.yaml")
        plugins = list(resolved.plugins)
        src_plugin = plugins[0]
        # Find a second plugin id
        tgt_plugin = next((p for p in plugins if p.id != src_plugin.id), None)
        assert tgt_plugin is not None
        original_meta = getattr(src_plugin.definition.setup, "meta", None)
        try:
            src_plugin.definition.setup.meta = {
                **(original_meta or {}),
                "relations": [
                    {"target": tgt_plugin.id, "kind": "governs"},
                    {"target": tgt_plugin.id, "kind": "delegates"},
                ],
            }
            plan = project_capability_plan(resolved)
            kinds = sorted(r.kind.value for r in plan.relations)
            assert "governs" in kinds
            assert "delegates" in kinds
        finally:
            src_plugin.definition.setup.meta = original_meta

    def test_validate_targets_disabled_passes_validation(self) -> None:
        """validate_targets=False 时不校验 target。"""
        resolved = resolve_profile("profiles/web-standard.yaml")
        plugin = next(iter(resolved.plugins))
        original_meta = getattr(plugin.definition.setup, "meta", None)
        try:
            plugin.definition.setup.meta = {
                **(original_meta or {}),
                "relations": [{"target": "any.target", "kind": "governs"}],
            }
            # Without validation, relation is preserved
            plan = project_capability_plan(
                resolved,
                options=CapabilityPlanOptions(validate_targets=False),
            )
            assert any(r.target == "any.target" for r in plan.relations)
        finally:
            plugin.definition.setup.meta = original_meta

    def test_non_list_relations_rejected(self) -> None:
        """meta.relations 不是 list → CapabilityPlanResolveError."""
        resolved = resolve_profile("profiles/web-standard.yaml")
        plugin = next(iter(resolved.plugins))
        original_meta = getattr(plugin.definition.setup, "meta", None)
        try:
            plugin.definition.setup.meta = {
                **(original_meta or {}),
                "relations": "not_a_list",
            }
            with pytest.raises(CapabilityPlanResolveError, match="must be list/tuple"):
                project_capability_plan(resolved)
        finally:
            plugin.definition.setup.meta = original_meta

    def test_non_mapping_relation_rejected(self) -> None:
        """relations[idx] 不是 mapping → CapabilityPlanResolveError."""
        resolved = resolve_profile("profiles/web-standard.yaml")
        plugin = next(iter(resolved.plugins))
        original_meta = getattr(plugin.definition.setup, "meta", None)
        try:
            plugin.definition.setup.meta = {
                **(original_meta or {}),
                "relations": ["not_a_dict"],
            }
            with pytest.raises(CapabilityPlanResolveError, match="must be mapping"):
                project_capability_plan(resolved)
        finally:
            plugin.definition.setup.meta = original_meta

    def test_source_defaults_to_plugin_id(self) -> None:
        """用户未指定 source → 默认 = plugin.id（self-relation）。"""
        resolved = resolve_profile("profiles/web-standard.yaml")
        plugin = next(iter(resolved.plugins))
        original_meta = getattr(plugin.definition.setup, "meta", None)
        try:
            plugin.definition.setup.meta = {
                **(original_meta or {}),
                "relations": [
                    {"target": plugin.id, "kind": "governs"}  # source not specified
                ],
            }
            plan = project_capability_plan(resolved)
            # relation.source defaults to plugin.id; target is same plugin.id
            for r in plan.relations:
                if r.kind is Relation.GOVERNS and r.target == plugin.id:
                    assert r.source == plugin.id
                    break
            else:
                pytest.fail("expected self-relation with kind=governs")
        finally:
            plugin.definition.setup.meta = original_meta
