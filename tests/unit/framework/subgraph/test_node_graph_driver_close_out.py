"""Driver close-out seam test (ADR-0219 §10.11.5).

Pins the contract that the inner→outer close-out is delegated to a
``SubgraphCloseOut`` instance, not to an inline literal tuple in the
graph driver. Asserts:

- the driver constructor accepts a ``close_out`` keyword and falls
  back to the cognition default when omitted;
- a stub ``SubgraphCloseOut`` implementation is honored: its
  ``project`` decides which fields appear on the outer port input
  and in what order — the driver's prior hard-coded
  ``("decision", "observation", "reflection", "response")`` tuple is
  gone;
- ``CLOSE_OUT_FIELDS`` in :mod:`lca.cognition.close_out` stays the
  single source of truth for the field set;
- ``PhaseOutput`` (channel) derives its field set from the same SSOT
  via :func:`lca.cognition.close_out.close_out_types`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.cognition.close_out import (
    CLOSE_OUT_FIELDS,
    CognitiveCloseOut,
    close_out_types,
)
from lca.contracts.subgraph import SubgraphCloseOut
from lca.framework.subgraph.plugins.channel import PhaseOutput


def test_close_out_fields_tuple_is_four_canonical_entries() -> None:
    assert CLOSE_OUT_FIELDS == ("decision", "observation", "reflection", "response")


def test_close_out_types_maps_each_field_to_a_typed_class() -> None:
    mapping = close_out_types()
    assert set(mapping.keys()) == set(CLOSE_OUT_FIELDS)
    for field_name in CLOSE_OUT_FIELDS:
        assert isinstance(mapping[field_name], type)


def test_phase_output_field_set_matches_close_out_fields() -> None:
    """The dynamic PhaseOutput derives its fields from the SSOT."""
    model_fields = set(PhaseOutput.model_fields.keys())
    assert set(CLOSE_OUT_FIELDS).issubset(model_fields)


def test_phase_output_rejects_extra_fields() -> None:
    import pytest

    # Imported lazily so the test file's static surface stays narrow.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PhaseOutput(unknown_field="x")  # type: ignore[call-arg]


def test_cognitive_close_out_first_non_none_wins_per_field() -> None:
    """Earlier outputs' non-None values are not overwritten by later None."""
    from lca.contracts.models.core.execution.decision import Decision

    d1 = Decision(decision_id="1", action_type="respond", rationale="r", confidence=0.9)
    inner: dict[str, PhaseOutput] = {
        "first": PhaseOutput(decision=d1),
        "second": PhaseOutput(),
    }
    close_out = CognitiveCloseOut()
    projected = dict(close_out.project(inner))
    assert projected == {"decision": d1}


class PriorityStub(SubgraphCloseOut):
    """Reverse the default priority: ``response`` wins over ``decision``."""

    def project(self, inner_outputs: Mapping[str, Any]) -> Mapping[str, Any]:
        projected: dict[str, Any] = {}
        for field_name in reversed(CLOSE_OUT_FIELDS):
            for output in inner_outputs.values():
                value = getattr(output, field_name, None)
                if value is not None:
                    projected[field_name] = value
                    break
        return projected


def _empty_spec() -> Any:
    from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
        BundleGraphNode,
        BundleGraphSpec,
    )

    node = BundleGraphNode(id="entry", region="think", factory="f", purpose="p")
    return BundleGraphSpec(id="t", region="think", purpose="p", nodes=(node,))


def test_driver_accepts_injected_stub_close_out() -> None:
    """A custom ``SubgraphCloseOut`` replaces the default projection."""
    from lca.framework.subgraph.plugins.node_graph_driver import NodeGraphDriver

    driver = NodeGraphDriver(
        spec=_empty_spec(),
        plan_ref="t",
        scope=object(),
        close_out=PriorityStub(),
    )
    assert isinstance(driver._close_out, PriorityStub)


def test_default_close_out_is_cognitive_when_omitted() -> None:
    from lca.framework.subgraph.plugins.node_graph_driver import NodeGraphDriver

    driver = NodeGraphDriver(spec=_empty_spec(), plan_ref="t", scope=object())
    assert isinstance(driver._close_out, CognitiveCloseOut)
