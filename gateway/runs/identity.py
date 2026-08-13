"""Who is acting. Isolation key for a Run.

A Run is one invocation of one AgentRef. Journal, sandbox, memory, and
inflight dedup are per identity. Two LobeHub agents that say the same
words are still two principals.

Housekeeper calls on /v1 are not agents and do not get an AgentRef.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gateway.modes import SOLO_ROLE

DEFAULT_AGENT_ID = "solo"


@dataclass(frozen=True)
class AgentRef:
    """Stable principal: id is the isolation key, name is the display role."""

    agent_id: str
    name: str


def default_agent_ref() -> AgentRef:
    return AgentRef(agent_id=DEFAULT_AGENT_ID, name=SOLO_ROLE)


def parse_agent_ref(raw: Any) -> AgentRef:
    """Parse POST /runs ``agent``. Missing or empty → default solo 助手."""
    if not isinstance(raw, dict):
        return default_agent_ref()
    agent_id = str(raw.get("id") or raw.get("agent_id") or "").strip()
    name = str(raw.get("name") or raw.get("role") or "").strip()
    if not agent_id and not name:
        return default_agent_ref()
    if not agent_id:
        agent_id = name
    if not name:
        name = SOLO_ROLE if agent_id == DEFAULT_AGENT_ID else agent_id
    return AgentRef(agent_id=agent_id, name=name)
