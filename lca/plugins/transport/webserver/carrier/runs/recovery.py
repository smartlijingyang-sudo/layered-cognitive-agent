"""Durable HIL resume recovery for the legacy /runs carrier.

A run paused at ``WAITING_INPUT`` holds its resumable traversal in
process-local ``RunSession`` state.  A kernel restart drops that state, so
the ask card in LobeHub still renders but ``POST /runs/<id>/answer`` can no
longer resume the run.

This module closes the gap with two pieces:

- :func:`write_resume_bundle` persists every fact needed to rebuild a paused
  run session at pause time (``<run_dir>/resume_bundle.json``).
- :func:`restore_waiting_run` lazily rebuilds a ``RunSession`` from that
  bundle when an answer arrives after a restart, re-assembling the mode
  runnable and the execution environment from the booted context.

The recovery path deliberately does not recreate the step-tree fold
machinery (``step_tree_bundle``/``thread_tree_writer`` stay ``None``), so the
original ``journal.json`` written at pause time is never overwritten by a
fresh Session that only contains recovery facts.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import structlog

from lca.plugins.transport.webserver.handlers.runs.session.session.session import (
    RunLifecycleStatus,
    RunRegistry,
    RunSession,
)

_log = structlog.get_logger(__name__)

_BUNDLE_NAME = "resume_bundle.json"
_BUNDLE_SCHEMA = "lca.run.resume_bundle/1"


# ---------------------------------------------------------------------------
# Persisting the pause (called from the lifecycle pause path)
# ---------------------------------------------------------------------------


def write_resume_bundle(session: RunSession) -> None:
    """Persist the durable resume facts for one paused run (best-effort)."""
    locator = getattr(session, "locator", None)
    if locator is None:
        return
    approval_request = getattr(session, "approval_request", None)
    snapshot = getattr(session, "snapshot", None)
    if not isinstance(approval_request, dict) or snapshot is None:
        return
    approval_id = approval_request.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        return
    try:
        from lca.plugins.session.runtime.resume.point import (
            resume_point_from_state_snapshot,
            serialize_resume_point,
        )

        resume_point = serialize_resume_point(
            resume_point_from_state_snapshot(approval_id, snapshot)
        )
    except Exception:
        _log.warning(
            "resume_bundle_serialize_failed",
            run_id=getattr(session, "run_id", ""),
            exc_info=True,
        )
        return
    agent = getattr(session, "agent", None)
    bundle = {
        "schema": _BUNDLE_SCHEMA,
        "run_id": session.run_id,
        "trace_id": session.trace_id,
        "question": session.question,
        "user_text": session.user_text,
        "mode": session.mode,
        "plan_ref": session.plan_ref,
        "agent_id": getattr(agent, "agent_id", "") or "",
        "agent_name": getattr(agent, "name", "") or "",
        "device_id": session.device_id,
        "plane": session.plane,
        "extra_plane": session.extra_plane,
        "execution_target": session.execution_target,
        "assistant_id": session.assistant_id,
        "user_id": session.user_id,
        "topic_id": session.topic_id,
        "origin": session.origin,
        "developer_seed": session.developer_seed,
        "developer_seed_job_id": session.developer_seed_job_id,
        "attachment_ids": list(session.attachment_ids or ()),
        "approval_request": approval_request,
        "resume_point": resume_point,
        "started_at": session.started_at,
    }
    try:
        run_dir = locator.run_dir(session.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        target = run_dir / _BUNDLE_NAME
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
    except Exception:
        _log.warning(
            "resume_bundle_write_failed",
            run_id=session.run_id,
            exc_info=True,
        )


def load_resume_bundle(run_id: str, locator: Any) -> dict[str, Any] | None:
    """Read the durable resume bundle for ``run_id``, or ``None``."""
    try:
        run_dir = locator.run_dir(run_id)
    except Exception:
        return None
    path = run_dir / _BUNDLE_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("run_id") != run_id:
        return None
    return data


# ---------------------------------------------------------------------------
# Lazy recovery (called from the answer/resume HTTP handlers)
# ---------------------------------------------------------------------------

_recovery_locks_guard = asyncio.Lock()
_recovery_locks: dict[str, asyncio.Lock] = {}


async def _recovery_lock(run_id: str) -> asyncio.Lock:
    async with _recovery_locks_guard:
        lock = _recovery_locks.get(run_id)
        if lock is None:
            lock = asyncio.Lock()
            _recovery_locks[run_id] = lock
        return lock


async def restore_waiting_run(
    registry: RunRegistry,
    ctx: Any,
    run_id: str,
    *,
    machine_resolver: Any = None,
) -> RunSession | None:
    """Rebuild a paused ``RunSession`` from its durable bundle, if any.

    Returns ``None`` when the run is not recoverable (no bundle, missing
    context, or reconstruction failure).  Idempotent under concurrent
    answer requests: only the first caller rebuilds, the rest reuse it.
    """
    locator = registry.locator()
    bundle = load_resume_bundle(run_id, locator)
    if bundle is None:
        return None
    async with await _recovery_lock(run_id):
        existing = registry.get(run_id)
        if existing is not None:
            return existing
        try:
            session = await _restore_from_bundle(
                registry,
                ctx,
                run_id,
                bundle,
                machine_resolver=machine_resolver,
            )
            registry.put(session)
            _log.info(
                "run_recovered_from_bundle",
                run_id=run_id,
                topic_id=session.topic_id,
            )
            return session
        except Exception:
            _log.warning(
                "run_restore_failed",
                run_id=run_id,
                exc_info=True,
            )
            return None


async def _restore_from_bundle(
    registry: RunRegistry,
    ctx: Any,
    run_id: str,
    bundle: dict[str, Any],
    *,
    machine_resolver: Any,
) -> RunSession:
    from lca.plugins.session.runtime.resume.point import (
        deserialize_resume_point,
        resume_point_to_state_snapshot,
    )
    from lca.plugins.transport.webserver.handlers.runs.session.builder.builder import (
        RunSessionBuilder,
    )
    from lca.plugins.transport.webserver.handlers.runs.session.setup.types import (
        RunSessionRequest,
    )
    from lca.plugins.transport.webserver.read.runs.identity import AgentRef

    resume_point = deserialize_resume_point(bundle.get("resume_point") or {})
    snapshot = resume_point_to_state_snapshot(resume_point)

    agent = AgentRef(
        agent_id=str(bundle.get("agent_id") or "solo"),
        name=str(bundle.get("agent_name") or "solo"),
    )
    request = RunSessionRequest(
        question=str(bundle.get("question") or ""),
        user_text=str(bundle.get("user_text") or ""),
        mode=str(bundle.get("mode") or "solo"),
        attachment_ids=tuple(bundle.get("attachment_ids") or ()),
        agent=agent,
        device_id=str(bundle.get("device_id") or ""),
        plane=str(bundle.get("plane") or ""),
        extra_plane=str(bundle.get("extra_plane") or ""),
        execution_target=str(bundle.get("execution_target") or ""),
        assistant_id=str(bundle.get("assistant_id") or ""),
        user_id=str(bundle.get("user_id") or ""),
        topic_id=str(bundle.get("topic_id") or ""),
        origin=str(bundle.get("origin") or "user"),
        developer_seed=str(bundle.get("developer_seed") or ""),
        developer_seed_job_id=str(bundle.get("developer_seed_job_id") or ""),
    )
    builder = RunSessionBuilder(registry, ctx=ctx)
    session = builder.build(
        request,
        restore={
            "run_id": run_id,
            "trace_id": str(bundle.get("trace_id") or f"trace_{run_id}"),
            "started_at": float(bundle.get("started_at") or 0),
            "plan_ref": str(bundle.get("plan_ref") or ""),
        },
    )
    session.status = RunLifecycleStatus.WAITING_INPUT
    session.approval_request = bundle.get("approval_request")
    session.snapshot = snapshot
    # Do not recreate the step-tree fold machinery: the pause-time
    # journal.json is the historical record and must not be overwritten.
    session.step_tree_bundle = None
    session.thread_tree_writer = None

    _seed_recovery_facts(session, bundle.get("resume_point") or {}, bundle)
    await _assemble_runnable(session, ctx, machine_resolver=machine_resolver)
    return session


def _seed_recovery_facts(
    session: RunSession,
    resume_point: dict[str, Any],
    bundle: dict[str, Any],
) -> None:
    """Seed the fresh Session with the durable recovery SSOT facts.

    The rebuilt session's journal starts from ``approval.persisted.v1`` +
    ``waiting_input`` checkpoint so ``recover_live_agent`` describes exactly
    one resumable state (ADR-0195 P4-S04).
    """
    approval_id = str(resume_point.get("approval_id") or "")
    if not approval_id:
        return
    approval_request = bundle.get("approval_request")
    pending = (
        _pending_tools_calling(approval_request) if isinstance(approval_request, dict) else None
    )
    from lca.contracts.harness.memory.events import ApprovalPersisted, SessionCheckpoint
    from lca.infrastructure.session.emit.lifecycle_emit import resolve_run_session_writer
    from lca.loop.fact_gateway import append_catalog_bound

    writer = resolve_run_session_writer(session)
    if writer is None:
        return
    append_catalog_bound(
        ApprovalPersisted(approval_id=approval_id, resume_point=resume_point),
        session=writer,
        actor="recovery",
    )
    append_catalog_bound(
        SessionCheckpoint(status="waiting_input", pending_tools_calling=pending),
        session=writer,
        actor="recovery",
    )


def _pending_tools_calling(approval_request: dict[str, Any]) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    tool_calls = approval_request.get("tool_calls")
    if isinstance(tool_calls, list):
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            arguments = call.get("arguments")
            pending.append(
                {
                    "tool_name": str(call.get("tool_name") or ""),
                    "call_id": str(call.get("call_id") or ""),
                    "arguments": arguments if isinstance(arguments, dict) else {},
                }
            )
    return pending


async def _assemble_runnable(
    session: RunSession,
    ctx: Any,
    *,
    machine_resolver: Any,
) -> None:
    """Rebuild the paused traversal's runnable + hot resume cache."""
    from lca.contracts.capabilities import RUN_MODE_REGISTRY
    from lca.contracts.mechanisms.capability.capability import require_capability
    from lca.plugins.transport.webserver.carrier.runs.execute.execution_environment import (
        RunExecutionEnvironment,
    )
    from lca.plugins.transport.webserver.carrier.runs.lifecycle.runnable_assembly import (
        CognitiveRunnableAssembler,
        RunnableAssemblyRequest,
    )

    mode_registry = require_capability(ctx, RUN_MODE_REGISTRY.key)
    llm_resolver = require_capability(ctx, "llm_resolver")
    assembler = CognitiveRunnableAssembler(mode_registry=mode_registry)
    environment = RunExecutionEnvironment(
        session,
        ctx=ctx,
        hub=session.hub,
        machine_resolver=machine_resolver,
    )
    async with environment.prepare() as prepared:
        runnable = await assembler.assemble(
            RunnableAssemblyRequest(
                session=session,
                question=session.question,
                mode=session.mode,
                observability=session.hub,
                bindings=prepared.bindings,
                scope=ctx,
                llm_resolver=llm_resolver,
                machine_resolver=machine_resolver,
            )
        )
        session.runnable = runnable


__all__ = [
    "load_resume_bundle",
    "restore_waiting_run",
    "write_resume_bundle",
]
