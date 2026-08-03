"""RunContext — typed metadata for one Agent/Team ``run`` call."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from lca.contracts.consultation import ConsultationState


@dataclass
class RunContext:
    """Per-invocation call metadata.

    Generic for every agent (solo / member / supervisor). Team
    *control-plane* state is not flattened here — when the caller is a
    hierarchical supervisor, pass a single ``consultation`` session
    object. Member tracing still uses ``from_role`` only.
    """

    trace_id: str | None = None
    from_role: str = ""
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    consultation: ConsultationState | None = None
    extra: dict[str, Any] = field(default_factory=dict)
