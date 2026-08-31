"""Append workspace artifact closure text before a legacy run journal is sealed."""

from __future__ import annotations

from typing import Any

import structlog

from lca.contracts.atoms.enums import StreamChannel
from lca.contracts.models.observability.journal import StepTextDelta
from lca.infrastructure.observability import BoundObservability
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession
from lca.plugins.transport.webserver.handlers.runs.terminal.status import journal_store

_log = structlog.get_logger(__name__)


def emit_artifact_closure_if_needed(
    workspace: Any,
    session: RunSession,
    hub: BoundObservability,
) -> None:
    """Append a text closure when the workspace contains materialized artifacts."""
    if workspace is None:
        return
    artifacts = workspace.artifacts.snapshot().artifacts
    if not artifacts:
        return
    closure = workspace.artifacts.closure_text()
    if not closure:
        return
    try:
        store = journal_store(hub)
        if store is not None:
            store.append(
                StepTextDelta(
                    step=-1,
                    text_delta="\n\n" + closure,
                    seq=0,
                    channel=StreamChannel.ANSWER.value,
                )
            )
        _log.info(
            "artifact_closure_emitted",
            hop="H2",
            run_id=session.run_id,
            artifact_count=len(artifacts),
            status=session.status.value,
        )
    except Exception:
        _log.warning("artifact_closure_emit_failed", hop="H2", run_id=session.run_id, exc_info=True)


__all__ = ["emit_artifact_closure_if_needed"]
