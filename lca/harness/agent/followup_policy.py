"""Built-in pure admission policies for concurrent Session follow-ups."""

from __future__ import annotations

from lca.contracts.protocols.session.session_turn import FollowupDispatch, SessionFollowupPolicy


class EnqueueFollowupPolicy(SessionFollowupPolicy):
    """Safely preserve follow-ups in FIFO order while a turn is active."""

    def decide(self, *, turn_active: bool) -> FollowupDispatch:
        return FollowupDispatch.ENQUEUE if turn_active else FollowupDispatch.START


class RejectFollowupPolicy(SessionFollowupPolicy):
    """Reject follow-ups while a Session has an active turn."""

    def decide(self, *, turn_active: bool) -> FollowupDispatch:
        return FollowupDispatch.REJECT if turn_active else FollowupDispatch.START


__all__ = ["EnqueueFollowupPolicy", "RejectFollowupPolicy"]
