"""Run-scoped async finalizer registry.

Modules register ``async def cleanup()`` callbacks during a run; the gateway
calls ``finalize_run()`` in its ``finally`` block so resources (sandbox
sessions, temp files, …) are released regardless of how the run ends.

Also provides ``current_run_id`` contextvar + ``run_id_scope`` context manager
so that any code within a run can discover its run_id without explicit
parameter threading.

Design notes
~~~~~~~~~~~~
* Callbacks run **concurrently** via ``asyncio.gather(return_exceptions=True)``
  — one failing finalizer must not block the others.
* Each callback is **one-shot**: auto-removed after ``finalize_run``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TypeAlias

import structlog

_log = structlog.get_logger(__name__)

Finalizer: TypeAlias = Callable[[], Awaitable[None]]

# run_id → list of async cleanup callables
_finalizers: dict[str, list[Finalizer]] = {}

# ── run_id ambient scope ────────────────────────────────────────────

_current_run_id: ContextVar[str] = ContextVar("lca_run_id", default="")


def get_current_run_id() -> str:
    """Return the active run_id, or empty string when unbound."""
    return _current_run_id.get()


@contextmanager
def run_id_scope(run_id: str) -> Iterator[str]:
    """Bind *run_id* for the duration of a run (gateway sets this)."""
    token: Token[str] = _current_run_id.set(run_id)
    try:
        yield run_id
    finally:
        _current_run_id.reset(token)


# ── finalizer registry ──────────────────────────────────────────────


def register_finalizer(run_id: str, callback: Finalizer) -> None:
    """Register an async cleanup callback for the given run."""
    _finalizers.setdefault(run_id, []).append(callback)


async def finalize_run(run_id: str) -> None:
    """Run all registered finalizers for *run_id*, then remove them.

    Safe to call even when no finalizers are registered (no-op).
    """
    callbacks = _finalizers.pop(run_id, None)
    if not callbacks:
        return
    results = await asyncio.gather(*[cb() for cb in callbacks], return_exceptions=True)
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            _log.warning(
                "run_finalizer_error",
                run_id=run_id,
                callback=callbacks[idx].__qualname__,
                error_type=type(result).__name__,
                error=str(result),
            )
