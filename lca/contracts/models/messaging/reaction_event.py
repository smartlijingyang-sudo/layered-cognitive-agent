"""Reaction-added session event contract.

``ReactionAddedCommitted`` is the durable catalog fact emitted when a reaction
is attached to a message (``react_to_message`` tool). It flows through
``Session.append`` → ``catalog_session_event_to_stamped`` →
``EventTranslator`` and reaches the LobeHub gateway as a ``reaction_added``
wire event.
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.harness.tasks.session import session_event


@session_event("reaction.added.v1", visibility="model")
@dataclass(frozen=True)
class ReactionAddedCommitted:
    """Durable reaction attachment fact for Session SSOT (maps to ``ReactionAdded``)."""

    message_id: str
    emoji: str
    actor: str
