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
from lca.plugins.think.classify.plugin import create_executor as create_think_classify_executor
from lca.plugins.think.gate.plugin import create_executor as create_think_gate_executor
from lca.plugins.think.reason.plugin import create_executor as create_think_reason_executor
from lca.plugins.think.route.plugin import create_executor as create_think_route_executor
from lca.plugins.think.shortcut.plugin import create_executor as create_think_shortcut_executor


def standard_phase_executors() -> Mapping[str, PhaseExecutor]:
    """Return the six standard phase executor implementations for focused runtime tests.

    ``phase.think.standard`` is the binding for ``think.main``; the 5-step
    think subgraph is driven by the declarative edge's ``subgraph_ref``.
    """

    return {
        "phase.perceive.standard": create_perceive_executor(),
        "phase.think.standard": create_think_executor(),
        "phase.think.shortcut": create_think_shortcut_executor(),
        "phase.think.route": create_think_route_executor(),
        "phase.think.reason": create_think_reason_executor(),
        "phase.think.classify": create_think_classify_executor(),
        "phase.think.gate": create_think_gate_executor(),
        "phase.act.standard": create_act_executor(),
        "phase.reflect.standard": create_reflect_executor(),
        "phase.remember.standard": create_remember_executor(),
        "phase.stop.standard": create_stop_executor(),
    }


def think_subgraph_dev_phase_executors() -> Mapping[str, PhaseExecutor]:
    """Alias kept for explicit opt-in reads; same set as :func:`standard_phase_executors`."""

    return standard_phase_executors()


__all__ = ["standard_phase_executors", "think_subgraph_dev_phase_executors"]
