"""RunContext — typed metadata for one Agent/Team ``run`` call."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from lca.contracts.member_status import MemberStatus


@dataclass
class RunContext:
    """Metadata for a single ``run`` invocation.

    Replaces free-form ``**context: str`` and the old InvocationContext name.
    """

    trace_id: str | None = None
    from_role: str = ""
    member_status: MemberStatus | None = None
    teammates_text: str = ""
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)
