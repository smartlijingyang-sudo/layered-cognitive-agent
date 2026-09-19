"""Build the cognitive ``RunContext`` projection from a gateway RunSession."""

from __future__ import annotations

from typing import Any

from lca.contracts.models.team.run.context import RunContext
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession


def run_context_for_session(session: RunSession) -> RunContext:
    """Project session identity and prior turns into the driver's input context."""
    extra: dict[str, Any] = {
        "agent_id": session.agent.agent_id,
        "agent_name": session.agent.name,
    }
    return RunContext(
        session_id=session.agent.agent_id,
        prior_turns=tuple(session.prior_turns) if session.prior_turns else (),
        extra=extra,
    )


__all__ = ["run_context_for_session"]
