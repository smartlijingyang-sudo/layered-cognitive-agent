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
    """Append a text closure when the workspace contains materialized artifacts.

    ADR-clean-truths 决策 二:fail / cancel 的 run 不再向 channel=answer 推产物闭合。
    仅 COMPLETED / DEGRADED 才发;其他状态(session.error 非空,或 status 已收敛到
    FAILED / CANCELED)直接 return。这样 run_fa054a09475f 那种 "已生成 PDF" 假成功
    答卷从源头消失。
    """
    if workspace is None:
        return
    # 决策 二:FAILED / CANCELED / session.error 非空 → 不再向 answer 推文本。
    if session.status.value in ("failed", "canceled"):
        _log.info(
            "artifact_closure_suppressed",
            hop="H2",
            run_id=session.run_id,
            status=session.status.value,
            reason="run failed or canceled",
        )
        return
    if session.error:
        _log.info(
            "artifact_closure_suppressed",
            hop="H2",
            run_id=session.run_id,
            status=session.status.value,
            reason="session.error non-empty",
        )
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
