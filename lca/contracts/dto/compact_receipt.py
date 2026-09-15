"""CompactReceipt — typed-boundary DTO emitted by ``think.context.compact``.

PR-3.8.2 typed-boundary node contract (borrowed-nodes spec §2.2). The
node reads ``state.budget`` and either runs an existing compaction
strategy (summarize / truncate_oldest / spill) or no-ops when the
budget is under the 0.7 ratio threshold. The receipt is the typed
evidence of the evaluation: it never raises out of the node boundary
(an exception path produces an empty receipt and re-routes the graph).

ADR-0195 §1.4 / C13: every cross-boundary transfer must be a frozen
Pydantic model with ``extra="forbid"``. The ``at`` field uses
:func:`lca.contracts.atoms.ids.ids.utc_now` (timezone-aware UTC); the
construction-time call keeps the receipt deterministic per node call
without leaking local time into the contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.ids.ids import utc_now

CompactStrategy = Literal["noop", "truncate_oldest", "summarize", "spill"]
"""Compact-operation strategy actually applied (or noop when under threshold)."""


class CompactReceipt(BaseModel):
    """Typed evidence of one ``think.context.compact`` evaluation.

    Fields:
        compacted: ``False`` when ratio < threshold (noop); ``True`` when
            a strategy ran and shrank the working context payload.
        bytes_before: payload size seen by the node, in bytes.
        bytes_after: payload size after compaction; equal to ``bytes_before``
            when ``compacted=False``.
        strategy: the literal name of the operation actually applied.
        at: UTC timestamp captured at node-call entry.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    compacted: bool
    bytes_before: int
    bytes_after: int
    strategy: CompactStrategy
    at: datetime

    @classmethod
    def noop(cls, *, bytes_seen: int) -> CompactReceipt:
        """Build the under-threshold receipt.

        ``bytes_after == bytes_before`` because nothing was compacted.
        ``strategy="noop"`` so downstream observers can branch on it.
        """
        return cls(
            compacted=False,
            bytes_before=bytes_seen,
            bytes_after=bytes_seen,
            strategy="noop",
            at=utc_now(),
        )

    @classmethod
    def applied(
        cls,
        *,
        bytes_before: int,
        bytes_after: int,
        strategy: CompactStrategy,
    ) -> CompactReceipt:
        """Build the over-threshold receipt for one applied strategy.

        ``strategy`` is asserted to be a non-``noop`` literal at the
        type level (the parameter type is the full ``CompactStrategy``
        so callers can pass any literal; the assertion below surfaces
        misuse loudly rather than producing a confusing noop receipt).
        """
        if strategy == "noop":
            raise ValueError(
                "CompactReceipt.applied requires a non-noop strategy; "
                "use CompactReceipt.noop() for the under-threshold path."
            )
        if bytes_after > bytes_before:
            raise ValueError(
                "CompactReceipt.applied must not grow the payload: "
                f"bytes_after={bytes_after} > bytes_before={bytes_before}"
            )
        return cls(
            compacted=True,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            strategy=strategy,
            at=utc_now(),
        )

    @classmethod
    def skipped(cls, *, bytes_seen: int) -> CompactReceipt:
        """Build the error-path receipt.

        The compaction module raised; the graph re-routes to
        ``think.route.decide``. The receipt keeps its typed shape
        (so downstream consumers never see ``None`` or an exception)
        but records ``strategy="noop"`` and ``compacted=False`` so
        traces are honest about what actually happened.
        """
        return cls(
            compacted=False,
            bytes_before=bytes_seen,
            bytes_after=bytes_seen,
            strategy="noop",
            at=utc_now(),
        )


__all__ = ["CompactReceipt", "CompactStrategy"]
