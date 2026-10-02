"""Model-visible turn history derivation (spec §B, ADR-0226).

Cognition must not import the concrete ``RunSessionWriter`` from ``lca.runtime``;
the session reader protocol (``SessionReader.derive_messages``) already exposes
the model-visible message list. This thin seam lets ``llm_turn`` depend on
infrastructure instead of runtime, keeping the dependency direction
``contracts -> infrastructure -> cognition -> runtime -> agent``.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.protocols.session.model.context import SessionReader


def derive_turn_history(session: SessionReader | None) -> list[dict[str, Any]]:
    """Return the model-visible message history for a bound session reader.

    ``None`` (no bound run session) yields an empty history so an unbound LLM
    turn still works without a journal.

    The wire shape is ``list[dict[str, Any]]`` — exactly what
    :meth:`SessionReader.derive_messages` returns. (The ``list[Message]``
    shape lives on the writer-side protocol only; the reader never had it.)
    """
    if session is None:
        return []
    return session.derive_messages()


__all__ = ["derive_turn_history"]
