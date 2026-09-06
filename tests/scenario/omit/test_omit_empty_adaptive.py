"""Regression: ``_omit_empty`` may not raise ``UnboundLocalError`` on non-empty
lists — see ADR-0122 (run_f03bd17f77f1 / seq=7/8/9 缺失).

The previous implementation used ``[pruned for item in value if ...]`` in the
list branch where ``pruned`` was only assigned in the Mapping branch.
First call into the list branch raised ``UnboundLocalError`` whenever a
non-empty list was reached; this corrupted every journal envelope with
``evidence: [...]`` (e.g. any RuntimeObserved carrying commit_evidence).
"""

from __future__ import annotations

from typing import Any

from lca.infrastructure.observability.journal.engine.journal_io import _omit_empty


def test_empty_list_at_top_returns_empty_list() -> None:
    assert _omit_empty([]) == []


def test_empty_list_in_dict_is_dropped() -> None:
    assert _omit_empty({"causation_refs": []}) == {}


def test_non_empty_list_of_ints_does_not_raise() -> None:
    """First non-empty list path triggers the old bug."""
    assert _omit_empty([1, 2, 3]) == [1, 2, 3]


def test_non_empty_list_of_dicts_does_not_raise() -> None:
    """First non-empty list of Mapping triggers the old bug."""
    assert _omit_empty([{"k": "v"}]) == [{"k": "v"}]


def test_dict_with_non_empty_list_value_does_not_raise() -> None:
    """Mapping-then-list (the actual trigger for seq=7/8/9 events)."""
    assert _omit_empty({"x": [{"k": "v"}], "y": []}) == {"x": [{"k": "v"}]}


def test_nested_mapping_with_empty_inner_list_does_not_raise() -> None:
    """Mapping → Mapping → empty list drops inner empty list & outer dict.

    Note: ``_omit_empty`` recursively drops empty containers, so
    ``{"a": {"b": []}}`` becomes ``{}`` (the inner empty list is dropped,
    making the inner dict empty, which is itself dropped).
    """
    assert _omit_empty({"a": {"b": []}}) == {}


def test_simulated_envelope_with_evidence_non_empty_does_not_raise() -> None:
    """Mirror the envelope that caused seq=7 projection failure."""
    envelope: dict[str, Any] = {
        "schema": "lca.journal/2",
        "data": {
            "kind": "plugin",
            "operation": "phase.fact",
            "source": "think.main",
            "outcome": "ok",
            "attributes": {
                "actor_role": "助手",
                "actor_step": 1,
                "plan_ref": "8638ea0484ac7f7f",
                "fact_id": "8638ea0484ac7f7f:think.main:1",
                "kind": "phase.result",
                "payload": {
                    "node": "think.main",
                    "semantic_phase": "think",
                    "result_kind": "phase_error",
                    "failure": {
                        "node_id": "think.main",
                        "attempts": (
                                {"attempt": 1, "category": "permanent", "error_type": "RuntimeError"},
                            ),
                        "attempt_count": 1,
                    },
                },
            },
            "retryable": False,
            "causation_refs": [1],
        },
        "evidence": [{"ref_id": "ev-1", "kind": "test"}],
    }
    out = _omit_empty(envelope)
    assert out["data"]["attributes"]["payload"]["failure"]["node_id"] == "think.main"
    assert out["evidence"] == [{"ref_id": "ev-1", "kind": "test"}]
