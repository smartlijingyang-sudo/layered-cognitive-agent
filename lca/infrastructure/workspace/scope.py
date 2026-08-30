"""Run Workspace ambient scope — gateway bind, contextvar access (ADR-0051)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from lca.contracts.atoms.ids import remaining_seconds, utc_now
from lca.contracts.models.core.budget import DEFAULT_RUN_WALL_CLOCK_SECONDS
from lca.infrastructure.workspace.artifact_ledger import ArtifactLedger

_current_workspace: ContextVar[RunWorkspace | None] = ContextVar("lca_run_workspace", default=None)


@dataclass
class RunWorkspace:
    """Unified run-scoped workspace: deadline + artifact ledger."""

    run_id: str
    deadline: datetime | None = None
    artifacts: ArtifactLedger = field(default_factory=ArtifactLedger)
    inspect_profile: dict[str, Any] | None = None

    def remaining_wall_seconds(self) -> float | None:
        if self.deadline is None:
            return None
        return remaining_seconds(self.deadline)


def get_run_workspace() -> RunWorkspace | None:
    return _current_workspace.get()


@contextmanager
def run_workspace_scope(
    run_id: str,
    *,
    wall_clock_seconds: int = DEFAULT_RUN_WALL_CLOCK_SECONDS,
) -> Iterator[RunWorkspace]:
    """Bind a RunWorkspace for the duration of a gateway run."""
    deadline = utc_now() + timedelta(seconds=wall_clock_seconds)
    workspace = RunWorkspace(run_id=run_id, deadline=deadline)
    token: Token[RunWorkspace | None] = _current_workspace.set(workspace)
    try:
        yield workspace
    finally:
        _current_workspace.reset(token)


def effective_agent_wall_clock(
    agent_cap: int | None,
    *,
    default_cap: int = DEFAULT_RUN_WALL_CLOCK_SECONDS,
) -> int | None:
    """Resolve agent wall clock as min(agent cap, workspace deadline remaining)."""
    cap = agent_cap if agent_cap is not None else default_cap
    workspace = get_run_workspace()
    if workspace is None or workspace.deadline is None:
        return cap
    remaining = workspace.remaining_wall_seconds()
    if remaining is None:
        return cap
    if remaining <= 0:
        return 0
    return max(1, int(min(float(cap), remaining)))
