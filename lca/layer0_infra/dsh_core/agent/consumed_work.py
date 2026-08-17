"""1:1 port of ``@deepseek-ai/dsh-agent/consumed-work.ts``."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.layer0_infra.dsh_core.session.types import (
    SessionEvent,
    TurnEndCompleted,
    TurnEndReason,
)


@dataclass(frozen=True)
class ConsumedWork:
    """How one agent log accounts for the work it consumed.

    The turn and step vocabulary alone cannot answer this.  A turn that stops
    before its first step leaves a ``turn/end`` shaped exactly like the balanced
    no-op turns a rejection or an empty claim produces, so reading turns in
    isolation either credits cut-short work as finished or convicts every no-op.
    The missing fact is the inbox's own record: :class:`Inbox` logs each
    mutation with ``removed_count`` and marks a cancellation
    ``outcome: 'canceled'``, which separates a turn claiming its input from
    work being dropped unrun.
    """

    end: SessionEvent | None = None
    """The latest closed turn that accounts for consumed work.

    One that entered a model step, or one that claimed inbox input and then
    failed, was stopped, or was rejected.  ``None`` when no turn closed over
    any work.
    """
    dropped_unrun: bool = False
    """Whether accepted work was cancelled out of the inbox, unrun, after that turn.

    This is the only account of input a cancellation took before any turn
    could open over it — no ``turn/end`` describes it.
    """


def _accounts_for_claim(reason: TurnEndReason) -> bool:
    """Whether a turn that consumed input but never reached a step accounts for it.

    Only a ``completed`` end does not: it had nothing left to run once its
    claim was rewritten away.  A ``blocked`` end is that input's ending too —
    the pre-step rejection that produced it discarded the claimed messages,
    so the work it took will never run.
    """
    # blocked, aborted, interrupted, error, max-tokens — all account for consumed input.
    # An unnameable ending over consumed input must not read as success.
    return not isinstance(reason, TurnEndCompleted)


def fold_consumed_work(events: Sequence[SessionEvent]) -> ConsumedWork:
    """Fold one agent log, or an owned suffix of one, into its account of consumed work.

    Single pass, and every input is the log itself: no caller has to sample
    live state before cancelling, so a cancellation issued by anyone — the
    owner's teardown, an ancestor's interrupt, an unloading plugin — reads
    the same.

    Returns the accounting turn when one closed, and whether work was dropped
    unrun after it.
    """
    stepped: set[int] = set()
    claimed: set[int] = set()
    open_turn: int | None = None
    end: SessionEvent | None = None
    dropped_unrun = False

    for event in events:
        event_type = event.type
        data = event.data if isinstance(event.data, dict) else {}

        if event_type == "turn/start":
            open_turn = data.get("turn")

        elif event_type == "step/start":
            stepped.add(data["turn"])

        elif event_type == "agent/inbox/spliced":
            removed_count = data.get("removed_count")
            if removed_count is None:
                continue
            outcome = data.get("outcome")
            inserted = data.get("inserted", ())
            # A replacement keeps the work pending under a new identity, so
            # only a cancellation that leaves nothing behind drops it.
            if outcome == "canceled":
                dropped_unrun = dropped_unrun or len(inserted) == 0
            # Claims are the loop's own step-boundary reads, always inside a turn.
            elif open_turn is not None:
                claimed.add(open_turn)

        elif event_type == "turn/end":
            turn = data["turn"]
            reason = data.get("reason")
            open_turn = None
            if turn in stepped:
                stepped.discard(turn)
                end = event
                dropped_unrun = False
            elif turn in claimed:
                claimed.discard(turn)
                if reason is not None and _accounts_for_claim(reason):
                    end = event
                    dropped_unrun = False

    if end is None:
        return ConsumedWork(dropped_unrun=dropped_unrun)
    return ConsumedWork(end=end, dropped_unrun=dropped_unrun)
