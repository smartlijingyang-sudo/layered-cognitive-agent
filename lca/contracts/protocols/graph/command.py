"""Command — typed control-plane port for ``intervene`` subgraph.

Per ADR-0228 §Decision 4: kernel reads a persisted ``Command`` from the
spine (observation) and re-projects it as a typed port via the
``intervene.resume`` node. The ``Command`` becomes a typed input to the
``think`` phase, replacing the implicit ``ask_user`` path through
``Decision.action_type``.

``Command`` is a control-plane artifact (it changes which node executes
next), but every emission lands in the journal as a ``SessionEvent``
first (observation), and the kernel reads from the journal projection —
not from a parallel channel. AGENTS.md §3 C7.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Command(BaseModel):
    """Typed pause / resume artifact crossing the ``intervene`` boundary.

    ``kind`` discriminates the four control-plane intents the
    ``intervene`` subgraph can carry:

    - ``approve``: user / policy approves the prior ``Decision``; resume
      as ``respond``.
    - ``reject``: user / policy rejects the prior ``Decision``; resume as
      ``respond`` with a ``rejected`` payload.
    - ``resume``: continue from where the run was paused; payload
      carries any state the resume path needs to restore.
    - ``redirect``: redirect the run to a different tool / action;
      payload carries the redirected tool call.

    ``issued_by`` is the control-plane actor (``"user" | "policy" |
    "system"``); ``issued_at_seq`` is the spine sequence number at the
    moment the command was issued — this anchors the resume path to a
    deterministic point in the journal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["resume", "approve", "reject", "redirect"]
    payload: dict[str, Any] | None = None
    issued_by: str
    issued_at_seq: int


__all__ = ["Command"]
