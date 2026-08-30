"""L3 Team entry shape — end-to-end team objective run.

Extracted from collaboration/agent.py (2026-08-30 cleanup). Teams are a
distinct collaboration primitive: one Team owns one objective end-to-end
and delegates to its composed members; an AgentUnit owns one task.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.message import AgentMessage
from lca.contracts.models.core.result import Result


@runtime_checkable
class TeamUnit(Protocol):
    """Team entry: run an objective end-to-end."""

    async def run(self, objective: str | AgentMessage) -> Result: ...
