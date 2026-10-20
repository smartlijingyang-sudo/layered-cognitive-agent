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
from collections.abc import Callable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class _BundleField:
    """One entry of the resume-bundle field inventory (RA-173).

    ``extract`` pulls the JSON-able value off a paused ``RunSession``
    (write side); ``read`` restores the typed value from a parsed bundle,
    applying the field's documented default when the key is absent or
    falsy. ``required`` marks fields whose absence means the bundle can
    never rebuild a real ``WAITING_INPUT`` session -- ``validate_bundle``
    rejects those bundles instead of letting them degrade downstream.
    """

    name: str
    required: bool
    extract: Callable[[RunSession], Any]
    read: Callable[[dict[str, Any]], Any]


def _bundle_str(name: str, default: str = "") -> Callable[[dict[str, Any]], str]:
    """Read one string field, falling back to its documented default."""
    return lambda bundle: str(bundle.get(name) or default)


def _agent_id_of(session: RunSession) -> str:
    return getattr(getattr(session, "agent", None), "agent_id", "") or ""


def _agent_name_of(session: RunSession) -> str:
    return getattr(getattr(session, "agent", None), "name", "") or ""


# The single inventory both write_resume_bundle and _restore_from_bundle
# walk. The structural keys (schema / run_id / approval_request /
# resume_point) are the load-seam contract owned by validate_bundle and stay
# out of this list. Optional-field defaults are intentional and documented
# per field; only ``question`` is required -- a resumed run without it
# renders a broken ask card (the zombie session this seam exists to prevent).
_BUNDLE_FIELDS: tuple[_BundleField, ...] = (
    _BundleField("trace_id", False, lambda s: s.trace_id, _bundle_str("trace_id")),
    _BundleField(
        "question",
        True,  # required: no question -> zombie ask card, reject the bundle
        lambda s: s.question,
        _bundle_str("question"),
    ),
    _BundleField("user_text", False, lambda s: s.user_text, _bundle_str("user_text")),
    # Missing mode falls back to the solo default the builder already assumes.
    _BundleField("mode", False, lambda s: s.mode, _bundle_str("mode", "solo")),
    _BundleField("plan_ref", False, lambda s: s.plan_ref, _bundle_str("plan_ref")),
    _BundleField("agent_id", False, _agent_id_of, _bundle_str("agent_id", "solo")),
    _BundleField("agent_name", False, _agent_name_of, _bundle_str("agent_name", "solo")),
    _BundleField("device_id", False, lambda s: s.device_id, _bundle_str("device_id")),
    _BundleField("plane", False, lambda s: s.plane, _bundle_str("plane")),
    _BundleField("extra_plane", False, lambda s: s.extra_plane, _bundle_str("extra_plane")),
    _BundleField(
        "execution_target",
        False,
        lambda s: s.execution_target,
        _bundle_str("execution_target"),
    ),
    _BundleField("assistant_id", False, lambda s: s.assistant_id, _bundle_str("assistant_id")),
    _BundleField("user_id", False, lambda s: s.user_id, _bundle_str("user_id")),
    _BundleField("topic_id", False, lambda s: s.topic_id, _bundle_str("topic_id")),
    # Missing origin keeps the pre-existing "user" default (ADR-0268 handoff runs set it).
    _BundleField("origin", False, lambda s: s.origin, _bundle_str("origin", "user")),
    _BundleField(
        "developer_seed", False, lambda s: s.developer_seed, _bundle_str("developer_seed")
    ),
    _BundleField(
        "developer_seed_job_id",
        False,
        lambda s: s.developer_seed_job_id,
        _bundle_str("developer_seed_job_id"),
    ),
    _BundleField(
        "attachment_ids",
        False,
        lambda s: list(s.attachment_ids or ()),
        lambda b: tuple(b.get("attachment_ids") or ()),
    ),
    _BundleField(
        "started_at",
        False,
        lambda s: s.started_at,
        lambda b: float(b.get("started_at") or 0),
    ),
    # RA-161: absent stays allowed so pre-2026-10-19 bundles keep loading;
    # a mistyped value is rejected by validate_bundle, not here.
    _BundleField(
        "loaded_namespaces",
        False,
        lambda s: sorted(s.loaded_namespaces),
        lambda b: frozenset(b.get("loaded_namespaces") or ()),
    ),
    # 生效的 namespace_approval 策略（per-assistant 覆盖后）。可选：旧 bundle
    # 缺省允许，resume 用全局默认；格式错误由 validate_bundle 拒绝。
    _BundleField(
        "namespace_approval",
        False,
        lambda s: dict(s.namespace_approval or {}),
        lambda b: dict(b.get("namespace_approval") or {}),
    ),
)


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
    bundle: dict[str, Any] = {
        "schema": _BUNDLE_SCHEMA,
        # Load-seam keys owned by validate_bundle (not the field
        # inventory): run identity + the two fail-closed payloads.
        "run_id": session.run_id,
        "approval_request": approval_request,
        "resume_point": resume_point,
    }
    # RA-173: the session-derived field inventory is walked here and in
    # _restore_from_bundle -- one list, no hand-mirrored copies.
    for field in _BUNDLE_FIELDS:
        bundle[field.name] = field.extract(session)
    if validate_bundle(bundle, session.run_id) is None:
        # The write side stays best-effort: a malformed bundle is skipped,
        # never raised, on the pause path.
        _log.warning(
            "resume_bundle_invalid_skip",
            run_id=session.run_id,
        )
        return
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


def validate_bundle(data: Any, run_id: str) -> dict[str, Any] | None:
    """Check a parsed resume bundle against the load contract.

    The load seam is the one place that decides what a resume bundle must
    contain: a non-dict JSON body, an ill-typed ``approval_request``, a
    missing ``approval_id``, an unparseable ``resume_point``, or a missing
    required inventoried field (``question``) all mean the bundle can never
    rebuild a real ``WAITING_INPUT`` session, so they are rejected here
    instead of degrading into a zombie session with silent defaults
    downstream.

    Returns the bundle when valid, ``None`` when corrupt.  ``None`` keeps
    mapping to the handler's existing "run not found" 404 path
    (``_run_is_recoverable`` / ``restore_waiting_run``).
    """
    if not isinstance(data, dict) or data.get("run_id") != run_id:
        return None
    approval_request = data.get("approval_request")
    if not isinstance(approval_request, dict):
        return None
    if (
        not isinstance(approval_request.get("approval_id"), str)
        or not approval_request["approval_id"]
    ):
        return None
    resume_point = data.get("resume_point")
    if not isinstance(resume_point, dict):
        return None
    try:
        from lca.plugins.session.runtime.resume.point import deserialize_resume_point

        # deserialize_resume_point is fail-closed (raises on any malformed
        # field), so the seam reuses it instead of hand-checking fields.
        deserialize_resume_point(resume_point)
    except Exception:
        return None
    loaded_namespaces = data.get("loaded_namespaces")
    # RA-161: this key used to bypass the load contract entirely -- a bare
    # string would silently become frozenset("abc") -> {"a", "b", "c"}
    # downstream in _restore_from_bundle. Absent stays allowed so
    # pre-2026-10-19 bundles keep loading (downstream "or ()" default).
    if loaded_namespaces is not None and (
        not isinstance(loaded_namespaces, list)
        or not all(isinstance(item, str) for item in loaded_namespaces)
    ):
        return None
    namespace_approval = data.get("namespace_approval")
    # 与 loaded_namespaces 同一原则：缺省允许（旧 bundle），但格式错误必须
    # 在 load seam 拒绝，避免把非 dict 策略静默恢复成全局默认。
    if namespace_approval is not None and (
        not isinstance(namespace_approval, dict)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in namespace_approval.items())
    ):
        return None
    for field in _BUNDLE_FIELDS:
        # RA-173: the inventory owns the required set. A bundle missing a
        # required field can never rebuild a real WAITING_INPUT session
        # (e.g. no question -> zombie ask card), so it is rejected here
        # instead of degrading to a silent default downstream.
        if field.required and data.get(field.name) is None:
            return None
    return data


def load_resume_bundle(run_id: str, locator: Any) -> dict[str, Any] | None:
    """Read the durable resume bundle for ``run_id``, or ``None``.

    Corrupt bundles are rejected at this seam (a structured warning is
    logged) and map to ``None`` exactly like a missing bundle.
    """
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
    bundle = validate_bundle(data, run_id)
    if bundle is None:
        _log.warning("resume_bundle_rejected", run_id=run_id)
    return bundle


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
    from lca.plugins.transport.webserver.agent_identity import AgentRef
    from lca.plugins.transport.webserver.handlers.runs.session.builder.builder import (
        RunSessionBuilder,
    )
    from lca.plugins.transport.webserver.handlers.runs.session.setup.types import (
        RunSessionRequest,
    )

    resume_point = deserialize_resume_point(bundle.get("resume_point") or {})
    snapshot = resume_point_to_state_snapshot(resume_point)

    # RA-173: read walks the same inventory the writer walked; every
    # default below lives on the field spec, documented there.
    restored = {field.name: field.read(bundle) for field in _BUNDLE_FIELDS}
    agent = AgentRef(
        agent_id=restored["agent_id"],
        name=restored["agent_name"],
    )
    request = RunSessionRequest(
        question=restored["question"],
        user_text=restored["user_text"],
        mode=restored["mode"],
        attachment_ids=restored["attachment_ids"],
        agent=agent,
        device_id=restored["device_id"],
        plane=restored["plane"],
        extra_plane=restored["extra_plane"],
        execution_target=restored["execution_target"],
        assistant_id=restored["assistant_id"],
        user_id=restored["user_id"],
        topic_id=restored["topic_id"],
        origin=restored["origin"],
        developer_seed=restored["developer_seed"],
        developer_seed_job_id=restored["developer_seed_job_id"],
    )
    builder = RunSessionBuilder(registry, ctx=ctx)
    session = builder.build(
        request,
        restore={
            "run_id": run_id,
            # The run_id-scoped trace fallback stays at the call site: the
            # inventory's read default for trace_id is "" (see the spec).
            "trace_id": restored["trace_id"] or f"trace_{run_id}",
            "started_at": restored["started_at"],
            "plan_ref": restored["plan_ref"],
        },
    )
    session.status = RunLifecycleStatus.WAITING_INPUT
    session.approval_request = bundle.get("approval_request")
    session.snapshot = snapshot
    session.loaded_namespaces = restored["loaded_namespaces"]
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
    from lca.contracts.harness.memory.events import ApprovalPersisted, SessionCheckpoint
    from lca.infrastructure.session.emit.lifecycle_emit import (
        pending_tools_calling_from,
        resolve_run_session_writer,
    )
    from lca.loop.fact_gateway import append_catalog_bound

    approval_request = bundle.get("approval_request")
    # The frontend-facing run id lives on the bundle (validate_bundle pins
    # bundle["run_id"] to the recovery target); never get_current_run_id().
    run_id = str(bundle.get("run_id") or "")
    pending = (
        pending_tools_calling_from(approval_request, run_id=run_id or None)
        if isinstance(approval_request, dict)
        else None
    )

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
    "validate_bundle",
    "write_resume_bundle",
]
