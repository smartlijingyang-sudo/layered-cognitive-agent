"""Typed think verdict — terminal projection of one think turn.

Per the 2026-09-09 think subgraph decompress plan (Task 4), ``verdict.v1``
is the typed fact that ``phase.think.verdict_emit`` emits at the think
subgraph's terminal sink. It packages the final ``Decision`` identity
with the gate chain that fired, the wall-clock timestamp, and the
source phase, so projection / replay / audit have one SSOT instead of
stitching ``decision`` + ``gate_chain`` strings from journal events.

Schema invariants enforced at construction (``__post_init__``):

- ``decision_id`` non-empty — the SSOT join key to ``Decision``.
- ``action_type`` non-empty — the projection discriminator.
- ``gate_chain`` non-empty tuple of non-empty strings — empty would
  mean "no gate fired" which is a bug, not a sentinel.
- ``ts`` timezone-aware — naive datetimes break replay determinism
  (AGENTS.md §3 C8).
- ``source_phase`` ∈ closed set — only ``"think"`` is wired today;
  adding a new emitter requires an ADR bump on the closed set.
- ``schema_version`` locked at ``VERDICT_SCHEMA_VERSION`` — bump
  = ADR bump; producers and consumers switch together.

The dataclass is frozen + slotted, so it is hashable and usable as
projection fold key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from lca.contracts.models.core.execution.decision import Decision

VERDICT_SCHEMA_VERSION: Final[str] = "v1"
_ALLOWED_SOURCE_PHASES: Final[frozenset[str]] = frozenset({"think"})


@dataclass(frozen=True, slots=True)
class Verdict:
    """Typed terminal fact emitted by one think turn."""

    decision_id: str
    action_type: str
    gate_chain: tuple[str, ...]
    ts: datetime
    source_phase: str
    schema_version: str = VERDICT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.decision_id, str) or not self.decision_id:
            raise ValueError("Verdict.decision_id must be a non-empty string")
        if not isinstance(self.action_type, str) or not self.action_type:
            raise ValueError("Verdict.action_type must be a non-empty string")
        if not isinstance(self.gate_chain, tuple) or not self.gate_chain:
            raise ValueError("Verdict.gate_chain must be a non-empty tuple")
        if not all(isinstance(label, str) and label for label in self.gate_chain):
            raise ValueError("Verdict.gate_chain entries must be non-empty strings")
        if not isinstance(self.ts, datetime) or self.ts.tzinfo is None:
            raise ValueError("Verdict.ts must be a timezone-aware datetime")
        if self.source_phase not in _ALLOWED_SOURCE_PHASES:
            raise ValueError(
                f"Verdict.source_phase must be one of "
                f"{sorted(_ALLOWED_SOURCE_PHASES)}, got {self.source_phase!r}"
            )
        if self.schema_version != VERDICT_SCHEMA_VERSION:
            raise ValueError(
                f"Verdict.schema_version must be {VERDICT_SCHEMA_VERSION!r}, "
                f"got {self.schema_version!r} (bump requires ADR)"
            )

    @classmethod
    def from_decision(
        cls,
        *,
        decision: Decision,
        gate_chain: tuple[str, ...],
        ts: datetime,
        source_phase: str = "think",
    ) -> Verdict:
        """Build a Verdict by mirroring Decision's decision_id + action_type.

        The caller's ``gate_chain`` and ``ts`` are passed explicitly so the
        emitter (Task 4's ``phase.think.verdict_emit``) owns the choice of
        which gates ran and which clock seam produced the timestamp —
        Verdict does not reach into either.
        """
        return cls(
            decision_id=decision.decision_id,
            action_type=decision.action_type,
            gate_chain=gate_chain,
            ts=ts,
            source_phase=source_phase,
        )


__all__ = ["VERDICT_SCHEMA_VERSION", "Verdict"]
