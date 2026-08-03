"""RunContext — typed metadata for one Agent/Team ``run`` call."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from lca.contracts.consultation import ConsultationState
from lca.contracts.routing import RoutingState


@dataclass
class RunContext:
    """Per-invocation call metadata.

    Generic for every agent (solo / member / supervisor). Team
    *control-plane* sessions are optional typed fields — never flatten
    board/retry/routing into ``extra`` (ADR-0026 / ADR-0027).
    """

    trace_id: str | None = None
    from_role: str = ""
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    consultation: ConsultationState | None = None
    routing: RoutingState | None = None
    extra: dict[str, Any] = field(default_factory=dict)
