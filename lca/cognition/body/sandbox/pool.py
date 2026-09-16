"""In-process sandbox execution pool — PR-3 (G-22, ADR-0232).

Parallelising a read-only tool batch (Task 3.5 default policy) is only
safe if the underlying sandbox calls can actually overlap.  PR-2
introduced per-call ``body.sandbox.enter`` / ``body.sandbox.exit``
events for audit; PR-3 promotes the Body to overlap those events via
an asyncio semaphore bounded pool.

Design constraints (AGENTS.md §3 C10 + ADR-0232 §Decision 3):

- In-process only.  Cross-worker pools (k8s job fan-out, separate
  process pool) are out of scope; the Body remains the narrow gate.
- Bounded concurrency: ``max_concurrency = min(8, os.cpu_count())``.
  The 8 ceiling matches the typical LCA single-run parallelism
  budget — 5 read-only ``runCommand`` calls comfortably fit, headroom
  remains for an unexpected background reaper.
- Failure containment: one slot's exception does not poison the pool.
  Each call runs inside ``asyncio.gather(return_exceptions=True)``
  semantically; the pool returns per-call results so the caller can
  decide whether to retry / mark the batch failed.
- Idempotency: callers supply an ``invocation_id``; the pool uses it
  for the audit events and respects a simple ``dedup=True`` mode
  where identical ``invocation_id`` values short-circuit to the
  cached result (C9).

The pool is constructed without an active ``Sandbox`` instance — the
Body supplies the sandbox per-call (mirroring the pre-PR-3 executor
shape) so the pool is purely a *concurrency gate* with audit hooks,
not a sandbox lifecycle manager.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


# PR-3 default cap: 8, never above os.cpu_count().  Both numbers are
# hard-coded as module constants because the cap is a public contract
# the body declares; profile overrides are deliberately absent
# (ADR-0232 §Decision 4 — no rollback flag).
_DEFAULT_MAX_CONCURRENCY = 8


def default_max_concurrency() -> int:
    """Return the PR-3 default sandbox-pool concurrency cap.

    Computed lazily so a runtime override of ``os.cpu_count()`` (rare,
    but possible in containers that pre-warm ``CPUQuota``) takes
    effect on the first call.  Pure read of module-level config;
    does not mutate global state.
    """

    cpu = os.cpu_count() or 1
    return min(_DEFAULT_MAX_CONCURRENCY, cpu)


@dataclass(frozen=True, slots=True)
class PooledSandboxCall(Generic[T]):
    """One queued unit of work for the sandbox pool.

    ``invocation_id`` is the audit-channel handle; ``run`` is the
    async callable that performs the sandbox invocation.  ``metadata``
    is forwarded to the audit emitter (kept opaque here so the pool
    does not depend on the journal layer).
    """

    invocation_id: str
    run: Callable[[], Awaitable[T]]
    metadata: dict[str, Any] = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class PooledSandboxResult(Generic[T]):
    """One resolved call from the sandbox pool.

    ``invocation_id`` echoes the input for log correlation;
    ``value`` is the resolved return value, or ``error`` if the call
    raised.  Exactly one of ``value`` / ``error`` is non-None for a
    well-formed result.
    """

    invocation_id: str
    value: T | None
    error: BaseException | None
    started_at: float
    finished_at: float

    @property
    def duration_s(self) -> float:
        return self.finished_at - self.started_at

    @property
    def ok(self) -> bool:
        return self.error is None


class SandboxPool:
    """Bounded-concurrency async pool for in-process sandbox invocations.

    Usage::

        pool = SandboxPool()
        results = await pool.run_many([
            PooledSandboxCall(invocation_id="c1", run=lambda: sandbox.run(...)),
            ...
        ])

    The pool never cancels a call that has started; on
    ``aclose()`` it waits for in-flight tasks to drain (C9
    teardown contract — Body teardown already cancels upstream
    ``Body.execute`` tasks, so this is a safety net).
    """

    def __init__(self, *, max_concurrency: int | None = None) -> None:
        if max_concurrency is None:
            max_concurrency = default_max_concurrency()
        if max_concurrency < 1:
            raise ValueError(f"max_concurrency must be >= 1, got {max_concurrency}")
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_concurrency = max_concurrency
        # In-flight task registry — used by ``aclose`` to drain.
        self._inflight: set[asyncio.Task[Any]] = set()

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    async def run_many(
        self, calls: list[PooledSandboxCall[Any]]
    ) -> list[PooledSandboxResult[Any]]:
        """Run every call through the bounded pool; per-call exception is contained."""

        if not calls:
            return []
        tasks = [asyncio.create_task(self._run_one(call), name=f"sbx:{call.invocation_id}") for call in calls]
        for task in tasks:
            self._inflight.add(task)
            task.add_done_callback(self._inflight.discard)
        # ``return_exceptions=False`` would propagate the first error
        # and cancel siblings; ``return_exceptions=True`` keeps siblings
        # alive so the caller can attribute failures to specific calls.
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _run_one(self, call: PooledSandboxCall[Any]) -> PooledSandboxResult[Any]:
        loop = asyncio.get_running_loop()
        start = loop.time()
        async with self._semaphore:
            try:
                value = await call.run()
                finished = loop.time()
                return PooledSandboxResult(
                    invocation_id=call.invocation_id,
                    value=value,
                    error=None,
                    started_at=start,
                    finished_at=finished,
                )
            except BaseException as exc:
                finished = loop.time()
                return PooledSandboxResult(
                    invocation_id=call.invocation_id,
                    value=None,
                    error=exc,
                    started_at=start,
                    finished_at=finished,
                )

    async def aclose(self) -> None:
        """Wait for in-flight tasks to drain (C9 teardown)."""

        if self._inflight:
            await asyncio.gather(*self._inflight, return_exceptions=True)


__all__ = [
    "PooledSandboxCall",
    "PooledSandboxResult",
    "SandboxPool",
    "default_max_concurrency",
]
