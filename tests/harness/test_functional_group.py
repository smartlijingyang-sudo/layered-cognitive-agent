"""Tests for FunctionalGroup 13 原语群分类学（ADR-0069 §一 + tracker §15.2）。"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.functional_group import (
    V3_TO_0069_MAPPING,
    FunctionalGroup,
    all_group_ids,
    parse_functional_group,
)


class TestFunctionalGroupEnum:
    def test_has_exactly_thirteen_members(self) -> None:
        """13 群 = G0..G12。"""
        members = list(FunctionalGroup)
        assert len(members) == 13

    @pytest.mark.parametrize(
        "expected_id",
        [f"G{i}" for i in range(13)],
    )
    def test_all_thirteen_group_ids_present(self, expected_id: str) -> None:
        assert FunctionalGroup(expected_id) is not None

    def test_canonical_values(self) -> None:
        assert FunctionalGroup.G0_CON_KERNEL.value == "G0"
        assert FunctionalGroup.G1_IDENTITY.value == "G1"
        assert FunctionalGroup.G6_DECISION.value == "G6"
        assert FunctionalGroup.G12_EVIDENCE.value == "G12"

    def test_str_enum_value_equality(self) -> None:
        assert FunctionalGroup.G6_DECISION == "G6"

    def test_no_duplicate_values(self) -> None:
        values = [g.value for g in FunctionalGroup]
        assert len(values) == len(set(values))

    def test_all_group_ids_returns_all(self) -> None:
        ids = all_group_ids()
        assert len(ids) == 13
        assert "G0" in ids
        assert "G12" in ids


class TestParseFunctionalGroup:
    def test_round_trip_string(self) -> None:
        for g in FunctionalGroup:
            assert parse_functional_group(g.value) is g

    def test_round_trip_enum(self) -> None:
        for g in FunctionalGroup:
            assert parse_functional_group(g) is g

    def test_unknown_string_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown functional group"):
            parse_functional_group("G99")

    def test_non_string_raises(self) -> None:
        with pytest.raises(TypeError):
            parse_functional_group(42)


class TestV3To0069Mapping:
    """v3 宪法 9 群 → ADR-0069 13 群映射（tracker §15.2）。"""

    def test_state_maps_to_facts(self) -> None:
        assert V3_TO_0069_MAPPING["State"] == (FunctionalGroup.G3_FACTS,)

    def test_perceive_maps_to_spacetime_and_perception(self) -> None:
        """v3 Perceive 拆成 G2 + G4 两群。"""
        assert V3_TO_0069_MAPPING["Perceive"] == (
            FunctionalGroup.G2_SPACETIME,
            FunctionalGroup.G4_PERCEPTION,
        )

    def test_think_maps_to_cognition(self) -> None:
        assert V3_TO_0069_MAPPING["Think"] == (FunctionalGroup.G5_COGNITION,)

    def test_gate_maps_to_decision(self) -> None:
        assert V3_TO_0069_MAPPING["Gate"] == (FunctionalGroup.G6_DECISION,)

    def test_act_maps_to_execution(self) -> None:
        assert V3_TO_0069_MAPPING["Act"] == (FunctionalGroup.G7_EXECUTION,)

    def test_memory_maps_to_facts(self) -> None:
        assert V3_TO_0069_MAPPING["Memory"] == (FunctionalGroup.G3_FACTS,)

    def test_collaboration_maps_to_collab(self) -> None:
        assert V3_TO_0069_MAPPING["Collaboration"] == (FunctionalGroup.G8_COLLAB,)

    def test_journal_maps_to_facts_and_evidence(self) -> None:
        """v3 Journal 收进 G3 + G12（事实 + 证据）。"""
        assert V3_TO_0069_MAPPING["Journal"] == (
            FunctionalGroup.G3_FACTS,
            FunctionalGroup.G12_EVIDENCE,
        )

    def test_composition_maps_to_composition(self) -> None:
        assert V3_TO_0069_MAPPING["Composition"] == (FunctionalGroup.G10_COMPOSITION,)

    def test_all_nine_v3_groups_present(self) -> None:
        """9 群全集（v3 宪法 §3.2）。"""
        expected = {
            "State",
            "Perceive",
            "Think",
            "Gate",
            "Act",
            "Memory",
            "Collaboration",
            "Journal",
            "Composition",
        }
        assert set(V3_TO_0069_MAPPING.keys()) == expected
