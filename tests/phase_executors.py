"""Explicit test-only assembly for the independently provided standard phases."""

from __future__ import annotations

from collections.abc import Mapping

from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseExecutor
from lca.plugins.phase_graph.act import create_executor as create_act_executor
from lca.plugins.phase_graph.perceive import create_executor as create_perceive_executor
from lca.plugins.phase_graph.reflect import create_executor as create_reflect_executor
from lca.plugins.phase_graph.remember import create_executor as create_remember_executor
from lca.plugins.phase_graph.stop import create_executor as create_stop_executor
from lca.plugins.phase_graph.think import create_executor as create_think_executor


def standard_phase_executors() -> Mapping[str, PhaseExecutor]:
    """Return the six profile plugin implementations for focused runtime tests."""

    return {
        "phase.perceive.standard": create_perceive_executor(),
        "phase.think.standard": create_think_executor(),
        "phase.act.standard": create_act_executor(),
        "phase.reflect.standard": create_reflect_executor(),
        "phase.remember.standard": create_remember_executor(),
        "phase.stop.standard": create_stop_executor(),
    }


__all__ = ["standard_phase_executors"]
