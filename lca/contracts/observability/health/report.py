"""``RunHealthReport`` + ``RunHealthSummary`` — top-level health DTOs (PR-1 / Task 1.1).

Upholds AGENTS.md §3 C13 (information bloodline closure) and §3 C8
(determinism): the report is a frozen Pydantic ``BaseModel`` with
``extra="forbid"``; ``conditions`` is a ``tuple`` (not ``list``) so the
report is hashable and identical spines produce identical reports.

Per spec
``docs/superpowers/specs/2026-09-16-run-health-and-execution-closure-design.md``
§10.5 (determinism property): callers may compare reports across calls
with ``==`` / dedupe with ``set`` / use as ``dict`` keys.

``RunHealthReport.__hash__`` is hand-rolled because ``RunHealthSummary.by_type``
is a plain ``dict`` (intentionally — see PR-1 contract code, no special
constraint beyond value type). Pydantic v2's auto-generated ``__hash__``
chokes on unhashable fields; we sort the items so the hash is stable
across dict insertion order. Equality still comes from the model-generated
``__eq__`` which compares the dict by value.

Every condition carries at least one ``EvidenceRef`` (spec §10.5 evidence
property, enforced by the fold — not by this DTO, which stays open so
intermediate state during a fold can carry an empty ``conditions`` tuple).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from lca.contracts.observability.health.condition import RunHealthCondition


class RunHealthSummary(BaseModel):
    """Aggregate counts + per-type status map for a ``RunHealthReport``.

    Counters MUST equal ``len(conditions)`` partitioned by ``status``.
    ``by_type`` keys are ``RunHealthCondition.type`` strings; values are
    the 4-value status alphabet.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    conditions_ok: int
    conditions_degraded: int
    conditions_failed: int
    conditions_unknown: int
    by_type: dict[str, Literal["ok", "degraded", "failed", "unknown"]]


class RunHealthReport(BaseModel):
    """Typed health report for one run.

    Frozen + ``extra="forbid"`` per AGENTS.md §3 C13. ``conditions`` is a
    tuple (not list) so the report is hashable and deterministic per
    AGENTS.md §3 C8 — see spec §10.5 for the determinism property.

    ``schema_version`` is the closed literal ``"1.0"``; bumping it is a
    breaking change and must follow AGENTS.md §5 (close the loop on
    Schema / Journal field changes — consumer, migration note, tests).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"]
    run_id: str
    generated_at: float
    conditions: tuple[RunHealthCondition, ...]  # tuple, hashable
    summary: RunHealthSummary

    def __hash__(self) -> int:
        # Pydantic v2's auto-generated ``__hash__`` fails on unhashable
        # fields (``summary.by_type`` is a ``dict``). Hand-roll a stable
        # hash over (schema_version, run_id, generated_at, conditions,
        # sorted summary pairs). Equality is still provided by Pydantic's
        # auto-generated ``__eq__`` which compares ``by_type`` by value.
        return hash(
            (
                self.schema_version,
                self.run_id,
                self.generated_at,
                self.conditions,
                (
                    "counters",
                    self.summary.conditions_ok,
                    self.summary.conditions_degraded,
                    self.summary.conditions_failed,
                    self.summary.conditions_unknown,
                ),
                tuple(sorted(self.summary.by_type.items())),
            )
        )


__all__ = ["RunHealthReport", "RunHealthSummary"]
