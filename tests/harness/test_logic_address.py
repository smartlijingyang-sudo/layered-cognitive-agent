"""Tests for LogicAddress 6 维 + V9 评分（ADR-0069 §二 + tracker §15.3）。"""

from __future__ import annotations

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.logic_address import (
    LogicAddress,
    canonical_scope_of,
    declared_dim_count,
    is_complete_address,
    logic_address_to_dict,
    score_level,
    score_logic_address,
)


class TestLogicAddressConstruction:
    def test_default_is_all_none(self) -> None:
        addr = LogicAddress()
        assert addr.functional_group is None
        assert addr.control_slot is None
        assert addr.scope is None
        assert addr.authority == ()
        assert addr.evidence == ()
        assert addr.revision is None

    def test_partial_address(self) -> None:
        addr = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
        )
        assert addr.functional_group is FunctionalGroup.G6_DECISION
        assert addr.control_slot is ControlSlot.THINK_GUARD

    def test_str_enum_inputs_accepted(self) -> None:
        """Plugin manifest may pass strings; LogicAddress normalizes to enum."""
        addr = LogicAddress(
            functional_group="G6",
            control_slot="think.guard",
            scope="run",
        )
        assert addr.functional_group is FunctionalGroup.G6_DECISION
        assert addr.control_slot is ControlSlot.THINK_GUARD
        assert addr.scope is Scope.RUN

    def test_empty_string_revision_normalized_to_none(self) -> None:
        addr = LogicAddress(revision="")
        assert addr.revision is None

    def test_authority_and_evidence_tuple_enforced(self) -> None:
        addr = LogicAddress(authority=("cap.budget",), evidence=("policy.x",))
        assert addr.authority == ("cap.budget",)
        assert addr.evidence == ("policy.x",)


class TestLogicAddressIsComplete:
    def test_default_is_not_complete(self) -> None:
        assert not is_complete_address(LogicAddress())

    def test_partial_is_not_complete(self) -> None:
        addr = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
        )
        assert not is_complete_address(addr)

    def test_full_address_is_complete(self) -> None:
        addr = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
            scope=Scope.RUN,
            revision="v1",
        )
        assert is_complete_address(addr)


class TestDeclaredDimCount:
    def test_default_has_two(self) -> None:
        """authority + evidence count by default (even when empty tuple)."""
        assert declared_dim_count(LogicAddress()) == 2

    def test_one_dim_added(self) -> None:
        assert declared_dim_count(LogicAddress(functional_group=FunctionalGroup.G6_DECISION)) == 3

    def test_all_four_scalar_dims_added(self) -> None:
        addr = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
            scope=Scope.RUN,
            revision="v1",
        )
        assert declared_dim_count(addr) == 6


class TestCanonicalScope:
    def test_invocation_alias(self) -> None:
        addr = LogicAddress(scope=Scope.INVOCATION)
        assert canonical_scope_of(addr) is Scope.TURN

    def test_run_unchanged(self) -> None:
        addr = LogicAddress(scope=Scope.RUN)
        assert canonical_scope_of(addr) is Scope.RUN

    def test_none_scope(self) -> None:
        addr = LogicAddress()
        assert canonical_scope_of(addr) is None


class TestToDict:
    def test_default_to_dict(self) -> None:
        d = logic_address_to_dict(LogicAddress())
        assert d["functional_group"] is None
        assert d["control_slot"] is None
        assert d["scope"] is None
        assert d["scope_canonical"] is None
        assert d["authority"] == []
        assert d["evidence"] == []
        assert d["revision"] is None

    def test_full_address_to_dict(self) -> None:
        addr = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
            scope=Scope.INVOCATION,
            authority=("gates.read",),
            evidence=("policy.x",),
            revision="v1",
        )
        d = logic_address_to_dict(addr)
        assert d["functional_group"] == "G6"
        assert d["control_slot"] == "think.guard"
        assert d["scope"] == "invocation"
        assert d["scope_canonical"] == "turn"  # alias applied
        assert d["authority"] == ["gates.read"]
        assert d["evidence"] == ["policy.x"]
        assert d["revision"] == "v1"


class TestScoreLogicAddress:
    """V9 LogicAddress 评分（tracker §15.3）。"""

    def test_empty_scores_zero(self) -> None:
        score = score_logic_address(LogicAddress())
        assert score.functional_group_hit is False
        assert score.control_slot_hit is False
        assert score.scope_hit is False
        assert score.evidence_hit is False
        assert score.total == 0
        assert score_level(score) == "missing"

    def test_partial_scores(self) -> None:
        addr = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
        )
        score = score_logic_address(addr)
        assert score.functional_group_hit is True
        assert score.control_slot_hit is True
        assert score.scope_hit is False
        assert score.evidence_hit is False
        assert score.total == 50
        assert score_level(score) == "partial"

    def test_three_dim_scores_75(self) -> None:
        addr = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
            scope=Scope.RUN,
        )
        score = score_logic_address(addr)
        assert score.total == 75
        assert score_level(score) == "good"

    def test_full_address_scores_100(self) -> None:
        addr = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
            scope=Scope.RUN,
            authority=("gates.read",),
            evidence=("policy.x",),
        )
        score = score_logic_address(addr)
        assert score.total == 100
        assert score_level(score) == "good"

    def test_evidence_hit_requires_non_empty_str(self) -> None:
        """Empty evidence tuple = no hit; non-string entry = no hit."""
        addr1 = LogicAddress(evidence=())
        assert score_logic_address(addr1).evidence_hit is False
        # Empty string in tuple also fails the all() check
        addr2 = LogicAddress(evidence=("ok", "", "more"))
        assert score_logic_address(addr2).evidence_hit is False
        # All non-empty strings = hit
        addr3 = LogicAddress(evidence=("a", "b"))
        assert score_logic_address(addr3).evidence_hit is True

    def test_score_level_thresholds(self) -> None:
        """≥75 good / 50-74 partial / <50 missing。"""
        # 25 (one dim) → missing
        addr25 = LogicAddress(functional_group=FunctionalGroup.G6_DECISION)
        assert score_level(score_logic_address(addr25)) == "missing"
        # 50 (two dims) → partial
        addr50 = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
        )
        assert score_level(score_logic_address(addr50)) == "partial"
        # 75 (three dims) → good
        addr75 = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
            scope=Scope.RUN,
        )
        assert score_level(score_logic_address(addr75)) == "good"
