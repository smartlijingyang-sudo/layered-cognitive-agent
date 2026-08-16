"""Core types, error classes, and plugin state machine.

PluginConfig is defined in ``lca.contracts.mechanisms.plugin`` (single source
of truth). This module re-exports it and defines runtime-only types.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from enum import Enum
from typing import Any

# Re-export PluginConfig from contracts (single source of truth)
from lca.contracts.mechanisms.plugin import PluginConfig as PluginConfig

# ── Callable aliases ───────────────────────────────────────

Cleanup = Callable[[], Any]
"""Disposer / cleanup function."""

Listener = Callable[..., Any]
"""Event listener callback."""

Apply = Callable[..., Any]
"""Plugin apply function (sync or async)."""

# ── Effect ─────────────────────────────────────────────────

Effect = Cleanup | Callable[[], Awaitable[Any]] | Iterable[Cleanup] | None
"""Plugin effect: disposer | async disposer | iterable of disposers | None."""

# ── Plugin state machine ──────────────────────────────────


class PluginState(str, Enum):
    """Plugin lifecycle states (Cordis ``Fiber.state``).

    PENDING → LOADING → ACTIVE → UNLOADING → DISPOSED
                          ↓
                        FAILED
    """

    PENDING = "pending"
    LOADING = "loading"
    ACTIVE = "active"
    FAILED = "failed"
    UNLOADING = "unloading"
    DISPOSED = "disposed"


# ── Errors ─────────────────────────────────────────────────


class PluginError(RuntimeError):
    """Plugin config, load, or lifecycle transition failure."""


class DependencyUnavailable(PluginError):  # noqa: N818 — mirrors Cordis naming
    """Required service not yet available (consumer stays PENDING)."""


# ── Bail predicate ─────────────────────────────────────────


def is_bailed(value: Any) -> bool:
    """Bail value = non-None and non-False (Cordis ``isBailed``)."""
    return value is not None and value is not False
