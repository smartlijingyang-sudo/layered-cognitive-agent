"""Durable resume entry for the /runs carrier (ADR-0195 P3-05, ADR-0191 B3).

``recover_live_agent`` (via ``transport_recovery``) is the authority for
whether a run may resume.  Process-local ``RunSession.snapshot`` /
``RunSession.runnable`` are a hot-path cache only — see P3-06 COMPAT.
"""

from __future__ import annotations

from lca.plugins.session.runtime.transport_recovery import assert_resume_allowed
from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry, RunSession


def validate_durable_resume(session: RunSession) -> None:
    """Fail-closed when Session facts disagree with a resume attempt."""
    bound = session.event_session
    if bound is None:
        return
    inner = getattr(bound, "inner", None) or getattr(bound, "session", None)
    snapshot = getattr(inner, "snapshot_events", None)
    if not callable(snapshot):
        return
    assert_resume_allowed(session, snapshot())


def resume_cache_ready(session: RunSession) -> bool:
    """Return whether the process-local resume cache can execute HIL resume.

    COMPAT(owner: ADR-0195 P3-06, from: RunSession.snapshot/runnable SSOT,
            to: recover_live_agent authority + cache-only runnable,
            delete_when: transport resume e2e 不依赖 snapshot 主路径,
            forbidden_new_usage: 新 resume 逻辑不得只写内存不 append facts)
    """
    return session.snapshot is not None and session.runnable is not None


async def resume_run(session: RunSession, registry: RunRegistry, answer: str) -> None:
    """Resume a paused run; durable Session facts gate acceptance."""
    validate_durable_resume(session)
    from lca.plugins.transport.webserver.carrier.runs.lifecycle import RunLifecycleCoordinator

    await RunLifecycleCoordinator(registry).resume(session, answer=answer)


__all__ = ["resume_cache_ready", "resume_run", "validate_durable_resume"]
