"""Stage IntEnum SSOT — single source of truth for boot phase identifiers."""

from __future__ import annotations

from lca_kernel.stages import Stage


def test_stage_values_one_through_six() -> None:
    assert [int(s) for s in Stage] == [1, 2, 3, 4, 5, 6]


def test_stage_names_are_k1_through_k5() -> None:
    names = {s.name for s in Stage}
    assert names == {
        "SOURCE",
        "RESOLVE",
        "TOPO",
        "PLAN",
        "BOOT",
        "OBSERVABILITY",
    }


def test_stage_lookup_by_name() -> None:
    assert Stage["SOURCE"] is Stage.SOURCE
    assert Stage["RESOLVE"] is Stage.RESOLVE


def test_stage_intenum_subclass() -> None:
    """Stage must be an IntEnum so values are comparable to plain ints."""
    from enum import IntEnum

    assert issubclass(Stage, IntEnum)


def test_stage_value_used_in_journal_event_label() -> None:
    """Stage int values appear in journal events; they must be plain ints."""
    value = int(Stage.BOOT)
    assert isinstance(value, int)
    assert value == 5
