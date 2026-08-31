"""Tests for lca_kernel package — Stage IntEnum SSOT contract.

Stage is the SSOT for boot phase identifiers used by BootJournalEvent.stage,
BootTrace, and ``lca-ops logs --scope boot`` filtering. These tests assert:

- The IntEnum values are exactly 1..6 (PR-2 D4 lock).
- The names are stable identifiers used by ADR-0115 §决定 1 K1..K5.
- The enum class supports iteration and lookup so plugin metadata can use
  ``Stage[name]`` to translate labels.
"""

from __future__ import annotations

from lca_kernel.stages import Stage


def test_stage_source_value_is_one() -> None:
    """D4: starting value must be 1 (distinguishes from journal seq=0)."""
    assert int(Stage.SOURCE) == 1


def test_stage_values_are_monotonic_one_through_six() -> None:
    """Six stages; no gaps, no duplicates."""
    values = [int(stage) for stage in Stage]
    assert values == [1, 2, 3, 4, 5, 6]


def test_stage_names_match_k1_through_k5() -> None:
    """Names must stay stable — used as ADR-0115 K identifiers in docs."""
    names = [stage.name for stage in Stage]
    assert names == ["SOURCE", "RESOLVE", "TOPO", "PLAN", "BOOT", "OBSERVABILITY"]


def test_stage_supports_name_lookup() -> None:
    assert Stage["SOURCE"] is Stage.SOURCE
    assert Stage["RESOLVE"].name == "RESOLVE"
    assert Stage["OBSERVABILITY"] is Stage.OBSERVABILITY


def test_stage_supports_iteration_in_declaration_order() -> None:
    members = list(Stage)
    assert len(members) == 6
    assert members[0] is Stage.SOURCE
    assert members[-1] is Stage.OBSERVABILITY


def test_stage_values_are_unique() -> None:
    values = [int(s) for s in Stage]
    assert len(values) == len(set(values))
