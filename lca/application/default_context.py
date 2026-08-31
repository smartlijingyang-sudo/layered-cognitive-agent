"""Own the process-default plugin context lifecycle for library callers.

This module concentrates the only mutable process-wide lifecycle needed by the
Layer-4 developer facade: a default Context may be booted once by either sync
or async callers, while concurrent event loops wait for the same result.

ADR-0115 决定 7: ``set_default_ctx`` is **deprecated** as of 2026-08-31 and
will be **removed by 2027-02-28**. Library callers should migrate to the
explicit ``lca_kernel.run_kernel()`` (or :func:`ensure_default_ctx`) and
receive the booted :class:`cordis.Context` as the ``scope=`` argument of
:class:`Agent` / :class:`Team`. ``set_default_ctx`` remains importable for
the deprecation window so that existing call sites still load, but it
emits a ``DeprecationWarning`` on every invocation.
"""

from __future__ import annotations

import asyncio
import threading
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cordis import Context

    from lca.harness.plugin_api import PluginContext

_DEFAULT_PROFILE = "profiles/web-standard.yaml"

# Public deprecation metadata (ADR-0115 决定 7).
SET_DEFAULT_CTX_DEPRECATION_REASON = (
    "set_default_ctx is deprecated; pass an explicit cordis Context as "
    "Agent(scope=...) / Team(scope=...) obtained from lca_kernel.run_kernel() "
    "or ensure_default_ctx(). Retire 2027-02-28."
)


@dataclass
class DefaultContextHolder:
    """Mutable state for one process-wide, lazily booted plugin context."""

    ctx: PluginContext | None = None
    boot_lock: threading.Lock = field(default_factory=threading.Lock)
    boot_complete: threading.Event = field(default_factory=threading.Event)
    booting: bool = False


holder = DefaultContextHolder()


def _claim_boot() -> tuple[bool, threading.Event]:
    """Claim the single process-wide boot or return its completion signal."""
    with holder.boot_lock:
        if holder.ctx is not None:
            return False, holder.boot_complete
        if not holder.booting:
            holder.booting = True
            holder.boot_complete.clear()
            return True, holder.boot_complete
        return False, holder.boot_complete


def _publish(ctx: Context | None) -> None:
    """Publish a completed boot, waking all concurrent callers on either outcome."""
    with holder.boot_lock:
        if ctx is not None:
            holder.ctx = ctx
        holder.booting = False
        holder.boot_complete.set()


def set_default_ctx(ctx: Context) -> None:
    """Bind an already-booted Cordis Context as the process default.

    .. deprecated:: 2026-08-31
        ``set_default_ctx`` is deprecated by ADR-0115 决定 7 and will be
        removed on **2027-02-28**. Use ``lca_kernel.run_kernel()`` (or
        :func:`ensure_default_ctx`) and pass the result as ``scope=`` to
        :class:`Agent` / :class:`Team` constructors.
    """
    warnings.warn(
        SET_DEFAULT_CTX_DEPRECATION_REASON,
        DeprecationWarning,
        stacklevel=2,
    )
    with holder.boot_lock:
        existing = holder.ctx
        if existing is not None and existing is not ctx:
            raise RuntimeError("default plugin context is already bound")
        holder.ctx = ctx
        holder.booting = False
        holder.boot_complete.set()


async def ensure_default_ctx() -> Context:
    """Return the default Context, coordinating lazy boot across event loops."""
    while True:
        if holder.ctx is not None:
            return holder.ctx
        owner, complete = _claim_boot()
        if not owner:
            await asyncio.to_thread(complete.wait)
            continue
        try:
            from lca.harness.profile.boot import boot_profile

            ctx = await boot_profile(_DEFAULT_PROFILE)
        except BaseException:
            _publish(None)
            raise
        _publish(ctx)
        return ctx


def get_or_create_default_ctx() -> Context:
    """Synchronously return the cached default Context outside an event loop.

    Callers already running inside an event loop must await ``ensure_default_ctx``
    or pass their already-booted scope explicitly. This prevents nested-loop
    bootstrapping while preserving one lifecycle owner for both calling styles.
    """
    if holder.ctx is not None:
        return holder.ctx

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        owner, complete = _claim_boot()
        if not owner:
            complete.wait()
            if holder.ctx is not None:
                return holder.ctx
            return get_or_create_default_ctx()
        try:
            from lca.harness.profile.boot import boot_profile

            ctx = asyncio.run(boot_profile(_DEFAULT_PROFILE))
        except BaseException:
            _publish(None)
            raise
        _publish(ctx)
        return ctx
    raise RuntimeError(
        "default plugin context is not booted; await ensure_default_ctx() "
        "or pass scope= from the already-booted cordis Context"
    )


# Emit a single deprecation notice on module import so existing apps
# surface the upcoming removal in their logs at startup.
warnings.warn(
    SET_DEFAULT_CTX_DEPRECATION_REASON,
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "SET_DEFAULT_CTX_DEPRECATION_REASON",
    "DefaultContextHolder",
    "ensure_default_ctx",
    "get_or_create_default_ctx",
    "holder",
    # NOTE: ``set_default_ctx`` is intentionally not exported. It remains
    # importable for the deprecation window but disappears from ``__all__``
    # so star-imports (``from lca.application.default_context import *``)
    # cannot bring it into new call sites by accident.
]
