"""Run-scoped ``SandboxRuntime`` registry — bound at run entry (ADR-0050)."""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from lca.contracts.mechanisms import consume
from lca.contracts.protocols import Sandbox
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.sandbox.runtime import RunBoundSandboxRuntime
from lca.layer0_infra.tools.run_finalizer import get_current_run_id, register_finalizer

_log = structlog.get_logger(__name__)

_runtimes: dict[str, RunBoundSandboxRuntime] = {}


def get_sandbox_runtime(run_id: str | None = None) -> RunBoundSandboxRuntime | None:
    """Return the runtime for *run_id* or the ambient run."""
    rid = (run_id or get_current_run_id()).strip()
    if not rid:
        return None
    return _runtimes.get(rid)


async def bind_sandbox_runtime(
    run_id: str,
    sandbox: Sandbox,
    store: FileStore,
    attachment_ids: Sequence[str] = (),
) -> RunBoundSandboxRuntime:
    """Create and register a run-bound runtime; idempotent per run_id."""
    cleaned = tuple(str(i).strip() for i in attachment_ids if str(i).strip())
    existing = _runtimes.get(run_id)
    if existing is not None:
        return existing

    runtime = RunBoundSandboxRuntime(
        sandbox=consume("sandbox", sandbox, RunBoundSandboxRuntime),
        store=store,
        run_id=run_id,
        attachment_ids=cleaned,
    )
    _runtimes[run_id] = runtime

    async def _destroy() -> None:
        await unbind_sandbox_runtime(run_id)

    register_finalizer(run_id, _destroy)
    _log.debug("sandbox_runtime_bound", run_id=run_id, attachments=len(cleaned))
    return runtime


async def ensure_sandbox_runtime(
    sandbox: Sandbox,
    store: FileStore,
    *,
    run_id: str | None = None,
    attachment_ids: Sequence[str] | None = None,
) -> RunBoundSandboxRuntime:
    """Get or create runtime for the active run and ensure environment ready."""
    rid = (run_id or get_current_run_id()).strip()
    if not rid:
        raise RuntimeError("sandbox runtime requires an active run_id scope")

    ids = attachment_ids if attachment_ids is not None else ()
    runtime = get_sandbox_runtime(rid)
    if runtime is None:
        runtime = await bind_sandbox_runtime(rid, sandbox, store, ids)

    err = await runtime.ensure_ready()
    if err is not None:
        _log.warning(
            "sandbox_runtime_not_ready",
            run_id=rid,
            summary=err.error_summary,
        )
    return runtime


async def unbind_sandbox_runtime(run_id: str) -> None:
    """Destroy and remove runtime for *run_id*."""
    runtime = _runtimes.pop(run_id, None)
    if runtime is None:
        return
    await runtime.destroy()
    _log.debug("sandbox_runtime_unbound", run_id=run_id)
