"""PortRegistry merge_output must overwrite (ADR-0217 §3.3.3 iron rule 5).

Regresses the run_2cd22760a828 ls-run loop: ``merge_output`` used
``setdefault``, so the first node's outputs (``decision``,
``observation``, ``reflection``) permanently shadowed the same
typed ports in every later outer-loop iteration. The stop-policy
then always saw the step-1 values and ``_delivery_satisfied_stop``
never unlocked, burning budget until ``max_visits: 8`` failed loud.

Verified by:

- ``merge_output`` with the same port name but a fresh DTO yields
  the fresh DTO in subsequent ``build_input`` calls.
- Iron rule 1 is preserved: ``set_outer_input`` still uses
  ``setdefault`` semantics (outer seed does not overwrite an
  already-written value).
- Cross-iteration simulation: two rounds of seed → execute →
  merge_output reuses the same ``PortRegistry`` instance; each
  round's typed-port snapshot matches the round's own outputs,
  not the previous round's.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.framework.graph.port_registry import PortRegistry


@dataclass(frozen=True, slots=True)
class FakeDecision:
    decision_id: str


def _reg() -> PortRegistry:
    return PortRegistry()


def test_merge_output_overwrites_same_port_name() -> None:
    reg = _reg()
    reg.merge_output({"decision": FakeDecision("step1")})
    reg.merge_output({"decision": FakeDecision("step2")})

    snapshot = reg.build_input(("decision",))
    assert snapshot.port_values["decision"].decision_id == "step2"


def test_set_outer_input_keeps_existing_value() -> None:
    """ADR-0217 §3.3.3 iron rule 1: outer seed never overwrites."""
    reg = _reg()
    reg.merge_output({"decision": FakeDecision("from_inner")})
    reg.set_outer_input({"decision": FakeDecision("from_outer_seed")})

    snapshot = reg.build_input(("decision",))
    assert snapshot.port_values["decision"].decision_id == "from_inner"


def test_set_outer_input_seeds_when_empty() -> None:
    reg = _reg()
    reg.set_outer_input({"decision": FakeDecision("seed")})
    assert reg.build_input(("decision",)).port_values["decision"].decision_id == "seed"


def test_outer_loop_two_rounds_typed_ports_fresh() -> None:
    """Simulate ``stop.main → perceive.main`` reusing one PortRegistry.

    Round 1 writes ``step1`` values; round 2 must read ``step2`` values
    on the same ports, not stale step-1 DTOs.
    """
    reg = _reg()
    reg.set_outer_input({"decision": FakeDecision("outer_seed_kept")})

    # Round 1 — step 1 think + act + reflect all run on the registry.
    reg.merge_output({"decision": FakeDecision("step1_think")})
    assert reg.build_input(("decision",)).port_values["decision"].decision_id == "step1_think"

    # Round 2 — outer loop comes back; merge_output must overwrite.
    reg.merge_output({"decision": FakeDecision("step2_think")})
    assert reg.build_input(("decision",)).port_values["decision"].decision_id == "step2_think"


def test_merge_output_unrelated_ports_are_independent() -> None:
    reg = _reg()
    reg.merge_output(
        {
            "decision": FakeDecision("d"),
            "observation": "obs",
            "reflection": "ref",
        }
    )
    reg.merge_output({"decision": FakeDecision("d2")})
    snap = reg.build_input(("decision", "observation", "reflection"))
    assert snap.port_values["decision"].decision_id == "d2"
    assert snap.port_values["observation"] == "obs"
    assert snap.port_values["reflection"] == "ref"
