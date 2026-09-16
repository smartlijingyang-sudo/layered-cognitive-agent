"""``HealthDeriver`` — structural Protocol for run-health derivers (PR-1 / Task 1.2).

Upholds AGENTS.md §3 C13 (information bloodline closure): this Protocol is
the D1 (definition) surface for the ``lca.health_derivers`` entry-point
group. The fold function in ``lca/plugins/observability/health/`` (Task 1.4)
loads registered derivers via ``importlib.metadata.entry_points`` and calls
``evaluate(events)`` on each — it never imports a specific deriver class
directly. D3 (transform) and D4 (consumer) live in
``lca/plugins/observability/health/`` (out of scope here).

Upholds AGENTS.md §5 (change closure): adding a new health dimension is a
single-line change to ``pyproject.toml`` + one new file in
``lca/plugins/observability/health/derivers/``. No contract change, no
fold change, no consumer change. (k8s admission-webhook / pluggy pattern.)

The Protocol is ``@runtime_checkable`` so consumers can do
``isinstance(impl, HealthDeriver)`` for adapter validation. The contract
is the Protocol, not the implementing class — implementation may subclass
or duck-type, both pass the structural check.

PR-1 ships with 8 deriver types: ``perceive``, ``think``, ``act``, ``tool``
(covers sandbox as a sub-rule per spec §15 G-21), ``llm``, ``reflect``,
``remember``, ``lifecycle``. Adding more is a pure addition.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.observability.health.condition import RunHealthCondition


@runtime_checkable
class HealthDeriver(Protocol):
    """A pluggable run-health deriver.

    Implementations consume a sequence of spine events (one run's worth)
    and emit zero or more ``RunHealthCondition`` observations. The fold
    function in ``lca/plugins/observability/health/run_health_fold.py``
    aggregates the per-deriver conditions into a single
    ``RunHealthReport``.

    The Protocol is structural and ``@runtime_checkable``: callers may
    use ``isinstance(impl, HealthDeriver)`` to validate adapters without
    requiring a base class.

    The ``events`` argument is the full ordered spine event sequence for
    one run. Derivers SHOULD NOT assume a specific sequence of event
    types; the fold is responsible for ordering and grouping.

    The returned ``list[RunHealthCondition]`` MUST satisfy spec §10.5
    evidence property: every condition carries
    ``len(evidence_refs) >= 1``. The fold does NOT re-validate this;
    the obligation lives with the deriver because the evidence is
    deriver-local.
    """

    def evaluate(self, events: list) -> list[RunHealthCondition]:  # type: ignore[type-arg]
        """Derive run-health conditions from one run's spine events.

        ``events`` is the full ordered spine event sequence for one
        run. Returns the conditions this deriver observes; the fold
        concatenates results across derivers. An empty ``list`` means
        "no observations" (legal but uncommon for a registered deriver).

        ``events`` is intentionally a bare ``list`` (not ``list[Any]`` or
        ``list[SpineEvent]``): the contract is "ordered sequence of spine
        events", the concrete element type is owned by the spine contract
        (``lca/contracts/observability/spine/``) and is not re-exported
        from this health contract to keep imports minimal. mypy sees the
        bare generic and we suppress the diagnostic with ``# type: ignore``.
        """
        ...


__all__ = ["HealthDeriver"]
