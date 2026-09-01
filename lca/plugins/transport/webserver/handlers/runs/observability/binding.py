"""Bind observability projections for one Gateway run.

This module owns the observability seam only: it extends the boot-provided
binding with run-local projections and can lazily repair the compatibility
path for sessions created by older callers. Session identity, registration,
and lifecycle transitions remain outside this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.contracts.observability.run_journal import LiveRunProjection, RunJournalFactory
from lca.contracts.protocols import JournalProjector
from lca.infrastructure.observability import BoundObservability
from lca.infrastructure.observability.facade.settings import ObservabilitySettings
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession


def assemble_run_hub(
    *,
    jsonl_writer: JournalProjector,
    tail: LiveRunProjection,
    ctx: Any,
    settings: ObservabilitySettings | None = None,
    extra_projectors: Sequence[JournalProjector] = (),
) -> BoundObservability:
    """Extend boot observability with immutable projections for one run."""
    del settings
    from lca.harness.observability import make_minimal_bound

    try:
        base: BoundObservability = require_capability(ctx, "observability")
    except MissingCapabilityError:
        from lca.infrastructure.observability.adapters.policy import AttributePolicy
        from lca.infrastructure.observability.facade import BoundObservability as FacadeBound

        minimal = make_minimal_bound()
        return FacadeBound(
            journal=minimal.journal,
            tracer=minimal.tracer,
            policy=AttributePolicy(),
            scorers=minimal.scorers,
        )

    run_bound = base.with_journal_projection(jsonl_writer)
    run_bound = run_bound.with_journal_projection(tail)
    for projection in extra_projectors:
        run_bound = run_bound.with_journal_projection(projection)
    return run_bound


def ensure_session_hub(
    session: RunSession,
    *,
    ctx: Any,
    settings: ObservabilitySettings | None = None,
) -> BoundObservability:
    """Lazily bind observability for a legacy session without creating it.

    ADR-0164 Phase 7: 显式为这个 session 构造 ``StepLifecycleStore`` 并
    注入到 journal factory, 让 step-tree backend 非空, terminalizer flush
    时 ``journal.json`` 才能真正被写出 (此前因 ContextVar 从未被 set,
    backend 一直是 None, journal.json 从未落盘)。
    """
    if session.hub is not None:
        return session.hub

    journal_factory = cast("RunJournalFactory", require_capability(ctx, "run_ledger_factory"))
    # 1) 先准备 lifecycle store (runtime 工厂, 不依赖 transport)
    lifecycle_store = _ensure_lifecycle_store(session)
    # 2) 注入到 factory → backend 拿到 store 后才能落盘
    components = journal_factory.create_run_components(
        jsonl_path=session.jsonl_path,
        lifecycle_store=lifecycle_store,
    )
    session.lifecycle_store = lifecycle_store
    session.tail = components.tail
    # ADR-0164 Phase 6: 把 step-tree bundle 挂到 session(terminalizer 用)
    session.step_tree_bundle = components.step_tree_writer
    hub = assemble_run_hub(
        jsonl_writer=components.writer,
        tail=components.tail,
        ctx=ctx,
        settings=settings,
    )
    session.hub = hub
    return hub


def _ensure_lifecycle_store(session: RunSession) -> object:
    """拿一个已 bind_run 的 ``StepLifecycleStore``(per-session 单例)。

    优先复用 session 上已存在的 store;否则新造一个。 session 上的 store
    只来自 ``ensure_session_hub`` 这一入口,保证每 session 一份。
    """
    existing = getattr(session, "lifecycle_store", None)
    if existing is not None:
        return existing
    from lca.runtime.journal_setup import BuildJournalMetadata, build_step_lifecycle_store

    agent = session.agent
    agent_role = (
        agent.name
        if agent is not None and agent.name
        else (agent.agent_id if agent is not None and agent.agent_id else "")
    )
    return build_step_lifecycle_store(
        run_id=session.run_id,
        trace_id=session.trace_id,
        metadata=BuildJournalMetadata(
            agent_role=agent_role,
            strategy_key=session.mode or "solo",
            objective=session.user_text or "",
            started_at=session.started_at,
        ),
    )


__all__ = [
    "_ensure_lifecycle_store",
    "assemble_run_hub",
    "ensure_session_hub",
]


__all__ = ["assemble_run_hub", "ensure_session_hub"]
