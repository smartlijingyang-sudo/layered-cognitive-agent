"""Regression test for ADR-0219 §4 cross-phase payload threading.

``RestrictedPhaseContext.payload_of(phase, want)`` reads from
``results_by_phase``. The legacy ``lca/loop/transaction.py`` driver
populates this mapping from ``PlanTraversal.results_by_phase`` and
threads it into every phase visit. The new kernel's
``PlanInterpreterAdapter._build_runner`` builds a fresh
``RestrictedPhaseContext`` per visit, but
``_build_phase_context`` does not pass a ``results_by_phase``
mapping. Every phase executor therefore sees an empty
``results_by_phase`` — the reflect/remember/stop phases all read
None for the prior think/act/reflect payloads and fall back to
no-ops. The stop phase returns ``StopDecision()`` with
``should_stop=False`` and the kernel loops on the
``stop.main -> perceive.main`` edge until ``PlanTraversal.visit``
raises ``max_visits=8 exceeded``.

These tests pin the missing contract: ``_build_phase_context`` MUST
accept and forward ``results_by_phase`` so ``payload_of`` returns
prior phase results instead of None.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import (
    PhaseResult,
    SemanticPhase,
)
from lca.framework.graph.adapter import _build_phase_context


def _decision(decision_id: str) -> Decision:
    return Decision(
        decision_id=decision_id,
        action_type=ActionType.USE_TOOL.value,
        rationale="smoke",
        confidence=0.9,
    )


def test_build_phase_context_forwards_results_by_phase() -> None:
    """The factory MUST accept and forward ``results_by_phase`` so
    ``payload_of(THINK, Decision)`` returns the prior think result."""
    prior_decision = _decision("prior-think")
    results_by_phase: dict[SemanticPhase, PhaseResult] = {
        SemanticPhase.THINK: PhaseResult(
            result_kind="decision",
            payload=prior_decision,
        ),
    }

    ctx = _build_phase_context(
        plan_ref="plan-x",
        node_ref="reflect.main",
        agent_state=None,
        journal=None,
        phase_observer=None,
        capabilities=None,
        results_by_phase=results_by_phase,
    )

    assert (
        ctx.payload_of(SemanticPhase.THINK, Decision) is prior_decision
    ), "reflect must see the prior think Decision via results_by_phase"


def test_build_phase_context_default_empty_when_omitted() -> None:
    """The kwarg is optional; omitting it preserves the empty mirror."""
    ctx = _build_phase_context(
        plan_ref="plan-x",
        node_ref="perceive.main",
        agent_state=None,
        journal=None,
        phase_observer=None,
        capabilities=None,
    )

    assert (
        ctx.payload_of(SemanticPhase.THINK, Decision) is None
    ), "without results_by_phase, payload_of returns None"


def test_build_phase_context_typed_lookups() -> None:
    """``payload_of(phase, want)`` returns the value iff it is an
    instance of ``want``; non-matching payloads resolve to None."""
    decision = _decision("typed")
    results_by_phase: dict[SemanticPhase, PhaseResult] = {
        SemanticPhase.THINK: PhaseResult(
            result_kind="decision",
            payload=decision,
        ),
    }

    ctx = _build_phase_context(
        plan_ref="plan-x",
        node_ref="reflect.main",
        agent_state=None,
        journal=None,
        phase_observer=None,
        capabilities=None,
        results_by_phase=results_by_phase,
    )

    assert ctx.payload_of(SemanticPhase.THINK, Decision) is decision
    # Wrong type: None even though the entry is present
    assert ctx.payload_of(SemanticPhase.THINK, dict) is None
    # Different phase: None
    assert ctx.payload_of(SemanticPhase.ACT, Decision) is None