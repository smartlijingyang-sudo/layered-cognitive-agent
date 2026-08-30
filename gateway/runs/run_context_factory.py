"""Build the cognitive ``RunContext`` projection from a gateway RunSession."""

from __future__ import annotations

from typing import Any

from gateway.runs.session import RunSession
from lca.contracts.models.core.conversation import PRIOR_CONVERSATION_WM_KEY
from lca.contracts.models.team.run_context import RunContext


def run_context_for_session(session: RunSession) -> RunContext:
    """Project session identity and prior turns into the driver's input context."""
    extra: dict[str, Any] = {
        "agent_id": session.agent.agent_id,
        "agent_name": session.agent.name,
    }
    if session.prior_turns:
        extra[PRIOR_CONVERSATION_WM_KEY] = [
            {"role": turn.role, "content": turn.content} for turn in session.prior_turns
        ]
    return RunContext(session_id=session.agent.agent_id, extra=extra)


__all__ = ["run_context_for_session"]
