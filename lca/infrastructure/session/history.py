"""Model-visible turn history derivation (spec §B, ADR-0226).

Cognition must not import the concrete ``RunSessionWriter`` from ``lca.runtime``;
the session reader protocol (``SessionReader.derive_messages``) already exposes
the model-visible message list. This thin seam lets ``llm_turn`` depend on
infrastructure instead of runtime, keeping the dependency direction
``contracts -> infrastructure -> cognition -> runtime -> agent``.
"""

from __future__ import annotations

from lca.contracts.models.session.message import Message
from lca.contracts.protocols.session.model.context import SessionReader


def derive_turn_history(session: SessionReader | None) -> list[Message]:
    """Return the model-visible message history for a bound session reader.

    ``None`` (no bound run session) yields an empty history so an unbound LLM
    turn still works without a journal.
    """
    if session is None:
        return []
    return session.derive_messages()


__all__ = ["derive_turn_history"]
