"""1:1 port of ``@deepseek-ai/dsh-agent/types.ts``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lca.layer0_infra.dsh_core.session._llm_types import UserMessage

# ---------------------------------------------------------------------------
# InboxTarget — one of the two ordered pending-message lists owned by an agent
# ---------------------------------------------------------------------------

InboxTarget = Literal["next-turn", "next-step"]
"""One of the two ordered pending-message lists owned by an agent."""


# ---------------------------------------------------------------------------
# SessionEventMap extension: agent/inbox/spliced
# ---------------------------------------------------------------------------

# In Python, there is no module augmentation.  We define the splice payload as
# a standalone dataclass so the Inbox and consumers can reference it directly.
# The session event bus dispatches these as ``agent/inbox/spliced`` events.


@dataclass(frozen=True)
class InboxSplicedPayload:
    """One normalized mutation of an agent's durable pending-message lists.

    Live dispatch precedes projection mutation, so synchronous observers may
    read the pre-splice inbox to recover the removed messages.
    """

    target: InboxTarget
    start: int
    removed_count: int | None = None
    inserted: tuple[UserMessage, ...] = ()
    outcome: Literal["canceled"] | None = None
