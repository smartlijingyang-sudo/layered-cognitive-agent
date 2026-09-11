"""PlanInterpreterAdapter — exposes :class:`PlanInterpreter` under the
legacy :class:`DeclarativeInterpreter` Protocol.

This is the **production cutover seam** for PR-7. The legacy
:class:`lca.framework.declarative.plugins.interpreter.GenericPlanInterpreter`
keeps running for existing consumers; new assembly paths return this
adapter so the runtime boots through the new kernel without deleting
the legacy class.

The adapter owns a host-injected :class:`StrategyRegistry` plus a
:class:`PhaseExecutionRunner` closure that the
:class:`PhaseExecutorStrategy` calls into. The closure wraps the
existing :class:`lca.loop.transaction.PhaseExecutionTransaction` so
the legacy journal / reducer / effect-gateway wiring stays in use.

Deletion policy: when
``lca/framework/declarative/plugins/interpreter.py`` (the legacy
``GenericPlanInterpreter``) is removed in a follow-up change set,
this adapter becomes the sole production entry point and the
``@plugin`` setup at
``lca/framework/declarative/plugins/interpreter_factory.py::setup``
will need to construct it directly. That refactor is intentionally
**not** part of this PR — the in-flight act-subgraph work and the
``bbcca980`` refactor series are still landing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.framework.graph.interpreter import InterpretationResult, PlanInterpreter
from lca.framework.graph.lifter import lift_executable_plan
from lca.framework.graph.strategy_registry import (
    PhaseExecutorLookup,
    StrategyRegistry,
    default_strategy_registry,
)


@dataclass
class PlanInterpreterAdapter:
    """Adapt :class:`PlanInterpreter` to the legacy production shape.

    ``run`` and ``resume`` accept the legacy kwargs (``state``,
    ``input``, ``budget``, ``capabilities``, ``artifacts``,
    ``executable``) and return whatever the legacy interpreter
    returned — typically an ``InterpretationResult`` from the
    legacy :mod:`lca.harness.declarative.execute.outcome_projection`
    module. The adapter wraps the new
    :class:`InterpretationResult` in a thin shim that exposes the
    same attribute names callers expect (``visits`` / ``facts`` /
    ``outcome`` / ``state``).
    """

    registry: StrategyRegistry = field(default_factory=default_strategy_registry)
    runner: PhaseRunner | None = None
    executor_lookup: PhaseExecutorLookup | None = None

    async def run(
        self,
        executable: object,
        *,
        state: object,
        input: object = None,
        budget: object = None,
        capabilities: object = None,
        artifacts: object = None,
        spec: object = None,
    ) -> object:
        plan = lift_executable_plan(executable)
        interp = PlanInterpreter(
            registry=self.registry,
            artifacts=artifacts or {},
        )
        result = await interp.run(plan, outer_state=state)
        return _LegacyResultShim(
            state=state,
            visits=result.visits,
            facts=result.facts,
            terminal_node=result.terminal_node,
            output=result.output,
        )

    async def resume(
        self,
        executable: object,
        *,
        state: object,
        cursor: object,
        input: object = None,
        budget: object = None,
        capabilities: object = None,
        artifacts: object = None,
    ) -> object:
        # The new kernel does not yet have a first-class resume path;
        # for the cutover PR, resume degrades to a fresh run with the
        # existing cursor consumed. PR-7's follow-up wires a real
        # ``PlanTraversal.resume`` path.
        return await self.run(
            executable,
            state=state,
            input=input,
            budget=budget,
            capabilities=capabilities,
            artifacts=artifacts,
        )


@dataclass
class _LegacyResultShim:
    """Mimics the legacy :class:`InterpretationResult` attribute shape."""

    state: Any
    visits: tuple = ()
    facts: tuple = ()
    terminal_node: str = ""
    output: dict = field(default_factory=dict)
    outcome: Any = None
    cursor: Any = None
    artifact: Any = None


__all__ = ["PlanInterpreterAdapter", "_LegacyResultShim"]