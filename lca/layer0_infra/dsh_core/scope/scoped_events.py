"""Generated scoped-event routing-subject resolvers for scope invariants.

1:1 port of ``@deepseek-ai/dsh-scope/scoped-events.generated.ts``.
Do not edit by hand; regenerate when event vocabulary changes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

ScopedSubjectResolver = Callable[[Sequence[object]], object]


def _agent_subject(args: Sequence[object]) -> object:
    payload = args[0]
    if hasattr(payload, "agent"):
        return payload.agent
    if isinstance(payload, dict):
        return payload.get("agent")
    return None


def _assembly_scope(args: Sequence[object]) -> object:
    payload = args[1]
    if hasattr(payload, "scope"):
        return payload.scope
    if isinstance(payload, dict):
        return payload.get("scope")
    return None


_UNDEFINED = object()

_SCOPED_SUBJECT_RESOLVERS: dict[str, ScopedSubjectResolver | None] = {
    "agent/created": _agent_subject,
    "agent/disposed": _agent_subject,
    "agent/error": _agent_subject,
    "agent/inbox/claimed": _agent_subject,
    "agent/inbox/discarded": _agent_subject,
    "agent/inbox/inserted": _agent_subject,
    "agent/pre-step": _agent_subject,
    "agent/request": _agent_subject,
    "agent/request-error": _agent_subject,
    "agent/session-start": _agent_subject,
    "agent/status": _agent_subject,
    "agent/turn-stopping": _agent_subject,
    "approval/request": _agent_subject,
    "goal/changed": _agent_subject,
    "session/created": None,
    "session/disposed": None,
    "session/event": None,
    "session/flush": None,
    "subagent/end": None,
    "subagent/start": None,
    "system-prompt/assemble": _assembly_scope,
    "tools/code-dispatch-log": _agent_subject,
    "tools/execute": _agent_subject,
    "tools/post-execute": _agent_subject,
    "tools/pre-execute": _agent_subject,
    "tools/result": _agent_subject,
}


def scoped_subject_resolver_for(
    event: str,
) -> ScopedSubjectResolver | object | None:
    """Resolve the routing key named by one scoped event payload.

    Returns:
    - A callable resolver when the event has a subject.
    - ``None`` for presence-only events (no extractable subject).
    - ``_UNDEFINED`` sentinel when the event is not scope-filtered.
    """
    if event in _SCOPED_SUBJECT_RESOLVERS:
        return _SCOPED_SUBJECT_RESOLVERS[event]
    return _UNDEFINED
