"""RunContext — typed metadata for one Agent/Team ``run`` call."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from lca.contracts.team_awareness import TeamAwareness


@dataclass
class RunContext:
    """Per-invocation call metadata.

    Generic for every agent (solo / member / lead). The lead's live team
    cognition uses the single optional ``team_awareness`` slot — never
    flatten board/retry/routing into ``extra`` .
    """

    trace_id: str | None = None
    from_role: str = ""
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    team_awareness: TeamAwareness | None = None
    extra: dict[str, Any] = field(default_factory=dict)
