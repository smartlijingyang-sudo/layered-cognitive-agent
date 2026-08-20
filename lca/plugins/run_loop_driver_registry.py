"""Run-loop driver registry + factory — Tier-3 plugin.

Hosts the driver registry on the ctx. The ``/runs`` HTTP carrier
(``gateway/runs/execute.py``) is a thin caller: it reads the active
driver from ``ctx.inject("run_loop_driver_registry")`` and delegates to
``driver.execute(ctx, ...)``.

Profiles swap drivers by enabling/disabling loop plugins. No
module-level singleton.
"""

from __future__ import annotations
from typing import Any
from lca.harness.plugin_api import plugin, PluginKind


class RunLoopDriverRegistry:
    """Target → driver registry. Loop plugins fill it at boot."""

    def __init__(self, default: str | None = None) -> None:
        self._drivers: dict[str, Any] = {}
        self._default = default

    def register(self, target: str, driver: Any) -> None:
        """Register a driver (or a zero-arg factory returning one) for ``target``.

        Idempotent: later registration wins (for profile-driven overrides).
        """
        self._drivers[target.strip().lower()] = driver

    def resolve(self, target: str) -> Any:
        key = target.strip().lower() if target else ""
        if not key:
            key = (self._default or "").strip().lower()
        try:
            entry = self._drivers[key]
        except KeyError as exc:
            raise _UnknownExecutionTargetError(target or self._default or "") from exc
        if callable(entry) and (not _looks_like_driver(entry)):
            return entry()
        return entry

    def targets(self) -> tuple[str, ...]:
        return tuple(sorted(self._drivers))


class _UnknownExecutionTargetError(RuntimeError):
    def __init__(self, target: str) -> None:
        super().__init__(
            f"no run_loop_driver registered for execution_target={target!r}; enable the corresponding loop plugin in your bundle"
        )
        self.target = target


def _looks_like_driver(obj: Any) -> bool:
    """Heuristic: a driver exposes ``async execute(...)``."""
    return callable(getattr(obj, "execute", None))


@plugin(
    id="lca-run-loop-driver-registry",
    provides=["run_loop_driver_registry"],
    requires=[],
    implements=[],
    layer="L1",
    effects="none",
    description="Empty run-loop driver registry; loop plugins fill it in.",
    test_suite="tests/test_plugin_tree_single_owner.py::test_empty_execution_target_uses_profile_default",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx, config: Any) -> None:
    """Provide an empty driver registry; loop plugins fill it in.

    Config shape::

        default: cognitive   # fallback target when request omits one
    """
    default = None
    if isinstance(config, dict):
        default = config.get("default")
    ctx.provide("run_loop_driver_registry", RunLoopDriverRegistry(default=default))
