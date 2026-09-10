"""Subgraph framework plugins.

Each module exposes a ``setup`` coroutine decorated by ``@plugin`` so
``profile`` / ``runtime_lifecycle_publisher`` can discover and load it
through Cordis.  Submodules are imported lazily so individual files can
land in their own commits without breaking sibling imports during the
batch-by-batch rollout (see plan §10).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.framework.subgraph.plugins import (  # noqa: F401
        channel,
        driver_signal,
        node_graph_driver,
        plan_lift,
        runner,
        runtime,
    )


_LAZY_SUBMODULES = frozenset(
    {
        "channel",
        "driver_signal",
        "node_graph_driver",
        "plan_lift",
        "runner",
        "runtime",
    }
)


def __getattr__(name: str):
    """Lazy-load individual framework plugin modules on first access."""
    if name in _LAZY_SUBMODULES:
        import importlib

        module = importlib.import_module(f"lca.framework.subgraph.plugins.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module 'lca.framework.subgraph.plugins' has no attribute {name!r}")


__all__ = sorted(_LAZY_SUBMODULES)
