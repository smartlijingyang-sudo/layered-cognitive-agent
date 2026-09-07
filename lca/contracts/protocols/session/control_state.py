"""Control-plane state fold contracts (ADR-0191 Wave C1).

``TurnControlProjection`` is the fold-based view that gates consume in
place of ``state.control_turns``. The contract is intentionally
protocol-only: it declares the read surface (``view``) and the deterministic
fold inputs (``init`` / ``apply``) without taking a dependency on any
plugin or runtime seam. The concrete fold lives at
``lca.plugins.session.session_turn_control.TurnControlUnit``; contract
consumers must only depend on this module (per ADR-0186 / ADR-0191 §C1).

Why a separate protocol (vs reuse of ``ProjectionUnit``):

- ``ProjectionUnit`` is the generic per-session fold contract used by
  ``ProjectionRegistry`` for cached snapshots. ``TurnControlProjection``
  is the gate-facing control-state read interface; the two concerns
  overlap but have different clients (cognition gates vs projection
  registry / cache). Keeping them separate prevents coupling gate
  semantics to registry mechanics.
- The data shape (``ControlState``) is the *view* exported to gates,
  not the raw fold row. Gates need structured fields
  (``turns``/``last_action_type``/``last_tool_name``), not arbitrary
  registry state.

C4 / C11 compliance:

- This module declares no I/O, no env reads, no logging. Fold
  determinism (C8) is the implementer's responsibility.
- No new event vocabulary is introduced; the fold operates on the
  existing ``turn.control.v1`` / ``turn.ended.v1`` /
  ``spine.runtime.reducer.apply`` facts that are already in the
  ``EXECUTION_POINTS`` whitelist (ADR-0191 §3.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ControlTurn:
    """One durable control-plane turn entry (gate-facing summary)."""

    action_type: str | None = None
    tool_name: str | None = None
    observation_success: bool | None = None
    tool_arguments: dict[str, Any] | None = None
    observation_payload: Any = None
    observation_error: str | None = None
    files_created: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ControlState:
    """JSON-serializable control-plane snapshot consumed by gates (ADR-0191 §C1).

    Not the model wire (that's ``ModelContextAssembler`` territory);
    not the durable fact stream (that's ``Session.append``). This is
    the gate-facing view derived from the ``turn_control`` fold.
    """

    turns: tuple[ControlTurn, ...] = ()
    last_action_type: str | None = None
    last_tool_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class TurnControlProjection(Protocol):
    """Fold Session facts into a control-plane view consumed by gates.

    The protocol matches the gate-facing read surface only. The concrete
    fold lives in
    ``lca.plugins.session.session_turn_control.TurnControlUnit``; this
    module must not import it (contracts layer must not depend on
    plugins layer).
    """

    def fold(self, session: Any) -> ControlState:
        """Build control state from a SessionReader / Session snapshot.

        Returns an empty :class:`ControlState` when ``session`` exposes no
        ``snapshot_events`` (no bound Session / cold path); never reads
        ``state.control_turns`` (gates may not read history — ADR-0191 §C1).
        """
        ...


__all__ = ["ControlState", "ControlTurn", "TurnControlProjection"]
