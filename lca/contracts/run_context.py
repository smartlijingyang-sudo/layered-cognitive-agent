"""RunContext — typed metadata for one Agent/Team ``run`` call."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from lca.contracts.enums import RoleMode
from lca.contracts.member_status import MemberStatus
from lca.contracts.role_team import RoleProfile


@dataclass
class RunContext:
    """Metadata for a single ``run`` invocation.

    Replaces free-form ``**context: str`` and the old InvocationContext name.
    """

    trace_id: str | None = None
    from_role: str = ""
    member_status: MemberStatus | None = None
    teammates: list[RoleProfile] = field(default_factory=list)
    role_mode: RoleMode = RoleMode.SOLO
    context_refs: list[str] = field(default_factory=list)
    deadline: datetime | None = None
    delegate_max_attempts: int = 3
    extra: dict[str, Any] = field(default_factory=dict)
