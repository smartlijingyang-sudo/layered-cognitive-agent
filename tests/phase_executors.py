"""Explicit test-only assembly for the independently provided standard phases."""

from __future__ import annotations

from collections.abc import Mapping

from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import PhaseExecutor
from lca.plugins.loop.phase.act.standard.plugin import create_executor as create_act_executor
from lca.plugins.loop.phase.perceive.standard.plugin import (
    create_executor as create_perceive_executor,
)
from lca.plugins.loop.phase.reflect.standard.plugin import (
    create_executor as create_reflect_executor,
)
from lca.plugins.loop.phase.remember.standard.plugin import (
    create_executor as create_remember_executor,
)
from lca.plugins.loop.phase.stop.standard.plugin import create_executor as create_stop_executor
from lca.plugins.loop.phase.think.standard.plugin import create_executor as create_think_executor
from lca.plugins.loop.phase.think.subgraph_host.plugin import (
    create_executor as create_think_subgraph_host_executor,
)


def standard_phase_executors() -> Mapping[str, PhaseExecutor]:
    """Return the seven profile plugin implementations for focused runtime tests.

    ``phase.think.subgraph_host`` is included because ``profiles/web-standard.yaml``
    binds ``think.main`` to it; tests resolving ``profiles/web-standard.yaml`` need
    the subgraph host registered alongside the six standard phase executors.
    """

    return {
        "phase.perceive.standard": create_perceive_executor(),
        "phase.think.standard": create_think_executor(),
        "phase.think.subgraph_host": create_think_subgraph_host_executor(),
        "phase.act.standard": create_act_executor(),
        "phase.reflect.standard": create_reflect_executor(),
        "phase.remember.standard": create_remember_executor(),
        "phase.stop.standard": create_stop_executor(),
    }


def think_subgraph_dev_phase_executors() -> Mapping[str, PhaseExecutor]:
    """Alias kept for explicit opt-in reads; same set as :func:`standard_phase_executors`."""

    return standard_phase_executors()


__all__ = ["standard_phase_executors", "think_subgraph_dev_phase_executors"]
