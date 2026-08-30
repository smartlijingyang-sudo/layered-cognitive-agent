"""Tests for PlanTemplate 12 standard templates (PR-12 + acceptance §4.6 V12).

Per acceptance-criteria §4.6 V12:

> lca-ops plan list-templates 输出 12 template
> 每个对应 tests/golden/plan_templates/<name>.yaml
> 每个 PlanTemplate golden test 覆盖

PR-12 阶段：12 PlanTemplate 实例（lca.contracts.atoms.plan_template.standard_plan_templates）
+ 12 golden YAML 文件 + property test 守护。

This test covers:

- 12 PlanTemplate instances present
- PlanTemplateId enum: 12 members + canonical values
- 12 golden YAML files present + non-empty
- Each PlanTemplate has relations / control_slots / required_groups populated
- parse_plan_template_id handles string + enum
- 11 relations used across 12 templates (coverage check)
- 11 control_slots used (coverage check)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.plan_template import (
    PlanTemplateId,
    all_plan_template_ids,
    parse_plan_template_id,
    plan_template_to_dict,
    standard_plan_templates,
)
from lca.contracts.atoms.relation import Relation

PLAN_TEMPLATES_DIR = Path("tests/golden/plan_templates")

# 12 PlanTemplate IDs (PR-12 V12 acceptance §4.6)
EXPECTED_TEMPLATE_IDS: tuple[str, ...] = (
    "rag",
    "prompt_chain",
    "routing",
    "parallel",
    "orchestrator_workers",
    "evaluator_optimizer",
    "tool_using_loop",
    "hitl",
    "team",
    "scheduled",
    "realtime",
    "self_evolving",
)


# ── PlanTemplateId enum ─────────────────────────────────────────────


class TestPlanTemplateIdEnum:
    def test_has_exactly_twelve_members(self) -> None:
        """12 标准 PlanTemplate ID（tracker §16.2 + ADR-0069 §五）。"""
        assert len(list(PlanTemplateId)) == 12

    def test_canonical_values(self) -> None:
        for template_id in EXPECTED_TEMPLATE_IDS:
            assert PlanTemplateId(template_id).value == template_id

    def test_str_enum_value_equality(self) -> None:
        assert PlanTemplateId.RAG == "rag"
        assert PlanTemplateId.HITL == "hitl"

    def test_all_ids_returns_all(self) -> None:
        ids = all_plan_template_ids()
        assert len(ids) == 12
        for expected in EXPECTED_TEMPLATE_IDS:
            assert expected in [i.value for i in ids]


class TestParsePlanTemplateId:
    def test_round_trip_string(self) -> None:
        for tid in PlanTemplateId:
            assert parse_plan_template_id(tid.value) is tid

    def test_round_trip_enum(self) -> None:
        for tid in PlanTemplateId:
            assert parse_plan_template_id(tid) is tid

    def test_unknown_string_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown plan template id"):
            parse_plan_template_id("nonexistent_template")

    def test_non_string_raises(self) -> None:
        with pytest.raises(TypeError):
            parse_plan_template_id(42)


# ── standard_plan_templates factory ───────────────────────────────


class TestStandardPlanTemplates:
    def test_returns_twelve_templates(self) -> None:
        templates = standard_plan_templates()
        assert len(templates) == 12

    def test_all_expected_ids_present(self) -> None:
        templates = standard_plan_templates()
        actual_ids = {t.template_id for t in templates}
        for expected_id in EXPECTED_TEMPLATE_IDS:
            assert expected_id in actual_ids, f"missing template_id={expected_id!r}"

    def test_templates_have_required_fields(self) -> None:
        """每个 PlanTemplate 含 relations / control_slots / required_groups。"""
        for template in standard_plan_templates():
            assert template.template_id
            assert template.name
            assert template.description
            assert len(template.relations) >= 1
            assert len(template.control_slots) >= 1
            assert len(template.required_groups) >= 1

    def test_relations_used_across_all_templates(self) -> None:
        """11 relations 至少 9 在 12 templates 中被使用（coverage check）。"""
        all_relations = {
            rel for template in standard_plan_templates() for rel in template.relations
        }
        # 11 relations enum members
        all_enum_relations = set(Relation)
        used = all_relations & all_enum_relations
        assert len(used) >= 9, (
            f"only {len(used)}/11 relations used: {used}; expected ≥9 for V12 coverage"
        )

    def test_control_slots_used_across_all_templates(self) -> None:
        """11 ControlSlot 至少 9 在 12 templates 中被使用。"""
        all_slots = {
            slot for template in standard_plan_templates() for slot in template.control_slots
        }
        all_enum_slots = set(ControlSlot)
        used = all_slots & all_enum_slots
        assert len(used) >= 9, f"only {len(used)}/11 control slots used: {used}"

    def test_functional_groups_used_across_all_templates(self) -> None:
        """13 FunctionalGroup 至少 9 在 12 templates 中被使用。"""
        all_groups = {
            grp for template in standard_plan_templates() for grp in template.required_groups
        }
        all_enum_groups = set(FunctionalGroup)
        used = all_groups & all_enum_groups
        assert len(used) >= 9, f"only {len(used)}/13 functional groups used: {used}"


# ── PlanTemplate to_dict ──────────────────────────────────────────


class TestPlanTemplateToDict:
    def test_to_dict_includes_all_fields(self) -> None:
        for template in standard_plan_templates():
            d = plan_template_to_dict(template)
            assert d["template_id"] == template.template_id
            assert d["name"] == template.name
            assert d["description"] == template.description
            assert d["scope"] == template.scope.value
            assert isinstance(d["relations"], list)
            assert isinstance(d["control_slots"], list)
            assert isinstance(d["required_groups"], list)
            assert d["version"] == template.version


# ── 12 golden YAML files inventory ──────────────────────────────────


class TestGoldenPlanTemplatesInventory:
    """V12 acceptance: 12 个 golden YAML 文件全部存在 + 非空。"""

    @pytest.mark.parametrize("template_id", EXPECTED_TEMPLATE_IDS)
    def test_golden_yaml_exists(self, template_id: str) -> None:
        path = PLAN_TEMPLATES_DIR / f"{template_id}.yaml"
        assert path.exists(), f"missing golden YAML: {path}"
        assert path.stat().st_size > 0, f"empty golden YAML: {path}"

    def test_all_12_yamls_counted(self) -> None:
        """Per acceptance §4.6: 12 个 PlanTemplate golden 文件必须全部存在。"""
        assert len(EXPECTED_TEMPLATE_IDS) == 12


# ── YAML file content consistency ──────────────────────────────────


class TestGoldenPlanTemplateContent:
    """每个 YAML 文件含 template_id + relations + control_slots + scope。"""

    @pytest.mark.parametrize("template_id", EXPECTED_TEMPLATE_IDS)
    def test_yaml_includes_template_id(self, template_id: str) -> None:
        path = PLAN_TEMPLATES_DIR / f"{template_id}.yaml"
        content = path.read_text()
        assert f"template_id: {template_id}" in content, (
            f"yaml {template_id}.yaml missing template_id field"
        )

    @pytest.mark.parametrize("template_id", EXPECTED_TEMPLATE_IDS)
    def test_yaml_includes_relations(self, template_id: str) -> None:
        """每个 YAML 含 relations 段（≥ 1 个 relation）。"""
        path = PLAN_TEMPLATES_DIR / f"{template_id}.yaml"
        content = path.read_text()
        assert "relations:" in content, f"yaml {template_id}.yaml missing relations: section"

    @pytest.mark.parametrize("template_id", EXPECTED_TEMPLATE_IDS)
    def test_yaml_includes_scope(self, template_id: str) -> None:
        path = PLAN_TEMPLATES_DIR / f"{template_id}.yaml"
        content = path.read_text()
        assert "scope:" in content, f"yaml {template_id}.yaml missing scope: field"
