"""Build the cognitive ``RunContext`` projection from a gateway RunSession."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.contracts.models.assistant.spec import (
    PROFILE_RUNTIME_AUTO_REVIEW_MODE,
    PROFILE_RUNTIME_VOCAL_MODE,
    PROFILE_RUNTIME_WAKE_SOURCE,
)
from lca.contracts.models.team.run.context import RunContext
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession

_ADR0248_PROFILE_KEYS = (
    PROFILE_RUNTIME_VOCAL_MODE,
    PROFILE_RUNTIME_AUTO_REVIEW_MODE,
    PROFILE_RUNTIME_WAKE_SOURCE,
)


def run_context_for_session(
    session: RunSession,
    profile_runtime: Mapping[str, object] | None = None,
) -> RunContext:
    """Project session identity and prior turns into the driver's input context.

    ``profile_runtime``（ADR-0248：来自 ``AssistantSpec.profile_runtime``，
    即 ``profile.json.runtime``）中的声带/审查/唤醒键会透传进
    ``RunContext.extra``，runtime loop 据此启用 gated 模式与 AutoReview。
    """
    extra: dict[str, Any] = {
        "agent_id": session.agent.agent_id,
        "agent_name": session.agent.name,
    }
    if profile_runtime:
        for key in _ADR0248_PROFILE_KEYS:
            if key in profile_runtime:
                extra[key] = profile_runtime[key]
    return RunContext(
        session_id=session.agent.agent_id,
        prior_turns=tuple(session.prior_turns) if session.prior_turns else (),
        extra=extra,
    )


__all__ = ["run_context_for_session"]
