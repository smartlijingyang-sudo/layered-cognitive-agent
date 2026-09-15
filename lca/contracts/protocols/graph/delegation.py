"""Delegation typed contracts (ADR-0228 D5).

Closed typed-port surface for the ``delegate`` cross-phase subgraph.
Replaces the implicit AGENT_FANOUT / AGENT_CONSULT strategy payloads
that previously crossed the kernel boundary as untyped dicts.

Three contracts, each a frozen Pydantic ``BaseModel`` with
``extra="forbid"`` (AGENTS.md §3 C13 typed Contract):

- :class:`DelegationRequest` — emitted by ``delegate.compose``; the
  fan-out payload the kernel dispatches to sub-agents.
- :class:`DelegationReceipt` — emitted by ``delegate.await``; the
  per-child status returned to the parent.
- :class:`FoldedDelegationResult` — emitted by ``delegate.fold``; the
  aggregated summary the parent uses to update its own Decision.

``idempotency_key`` on the request satisfies C9 (safe retry).
Capability monotonicity (C5) is enforced at the kernel boundary
against the parent's grant; the contracts carry no authority data of
their own.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class DelegationRequest(BaseModel):
    """Typed fan-out request per ADR-0228 D5.

    ``delegate_to`` is the ``semantic_name`` of the target agent, or
    ``"*"`` for a kernel-dispatched broadcast. ``payload`` is a
    closed-shape bag (the parent decides the keys); ``idempotency_key``
    is required for retry safety (C9).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    delegate_to: str
    payload: dict[str, Any]
    timeout_ms: int = 30_000
    idempotency_key: str | None = None


class DelegationReceipt(BaseModel):
    """Receipt from a single sub-agent per ADR-0228 D5.

    ``delegate_from`` is the ``semantic_name`` that produced the
    receipt (round-trips with the request's ``delegate_to``). Exactly
    one of ``payload`` / ``error`` is meaningful per status; the
    model does not enforce that mutual exclusion because a timeout /
    cancel may carry a partial payload for diagnostics.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    delegate_from: str
    status: Literal["ok", "error", "timeout", "cancelled"]
    payload: dict[str, Any] | None = None
    error: str | None = None


class FoldedDelegationResult(BaseModel):
    """Aggregated result from ``delegate.fold`` per ADR-0228 D5.

    The folded payload is a closed-shape ``dict[str, Any]`` whose keys
    the parent decides. The aggregate counts are derived from the
    receipts the fold consumed; they let the parent short-circuit on
    a fully-failed fan-out without re-walking ``folded_payload``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_count: int
    ok_count: int
    error_count: int
    folded_payload: dict[str, Any]


__all__ = [
    "DelegationReceipt",
    "DelegationRequest",
    "FoldedDelegationResult",
]
