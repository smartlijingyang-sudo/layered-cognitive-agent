"""Explicit test-only assembly for the independently provided standard phases."""

from __future__ import annotations

from collections.abc import Mapping

from lca.contracts.protocols.declarative.declarative_2.declarative_phase_graph import PhaseExecutor
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


def standard_phase_executors() -> Mapping[str, PhaseExecutor]:
    """Return the six standard phase executor implementations for focused runtime tests.

    think.main 走 ``bundles/think.yaml`` 5 步子图(Node Note
    2026-09-09-phase-node-sub-spec-ref),interpreter 通过节点级
    ``sub_spec_ref`` 直接挂子图,不调用 phase executor。
    """

    return {
        "phase.perceive.standard": create_perceive_executor(),
        "phase.reflect.standard": create_reflect_executor(),
        "phase.remember.standard": create_remember_executor(),
        "phase.stop.standard": create_stop_executor(),
    }


def think_subgraph_dev_phase_executors() -> Mapping[str, PhaseExecutor]:
    """Alias kept for explicit opt-in reads; same set as :func:`standard_phase_executors`."""

    return standard_phase_executors()


__all__ = ["standard_phase_executors", "think_subgraph_dev_phase_executors"]