"""Close a plan-bound AgentGraph into one production CognitiveRuntime.

This adapter deliberately owns only orchestration: validate the graph, close
plan-declared mechanics, and pass the resulting immutable dependency bundle to
the production factory. Capability lookup details live in
``runtime_capabilities`` so they can be reviewed and tested independently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.protocols import Runtime
from lca.contracts.protocols.runtime.runtime_composition import RuntimeFactory
from lca.plugins.composer.internal.runtime_binding import bind_runtime_graph
from lca.plugins.composer.internal.runtime_capabilities import (
    RuntimeCapabilityClosure,
    resolve_runtime_capabilities,
)

if TYPE_CHECKING:
    from cordis import Context

    from lca.contracts.harness.composer import AgentGraph
    from lca.contracts.protocols.state.plan import CompiledRunPlan
    from lca.contracts.protocols.journal.spec import AgentSpec


def assemble_runtime_from_graph(
    spec: AgentSpec,
    graph: AgentGraph,
    *,
    plan: CompiledRunPlan,
    scope: Context,
) -> Runtime:
    """Build one runtime from a complete graph and its immutable plan.

    The graph holds capabilities selected by AgentGraph composers. Remaining
    mechanics are resolved exclusively through the provider bindings declared
    in ``plan``; a missing binding therefore fails during composition instead
    of silently selecting a fallback while executing a turn.
    """

    capabilities = resolve_runtime_capabilities(plan, scope)
    bindings = bind_runtime_graph(
        capabilities,
        spec=spec,
        graph=graph,
        plan=plan,
        scope=scope,
    )
    factory = capabilities.runtime_factory
    if not isinstance(factory, RuntimeFactory):
        raise TypeError(
            f"runtime_factory must implement RuntimeFactory, got {type(factory).__name__}"
        )
    return _require_runtime(factory.create(bindings))


def _require_runtime(candidate: object) -> Runtime:
    """Reject an incompatible loop provider at the composition boundary."""

    if not isinstance(candidate, Runtime):
        raise TypeError(
            f"runtime_factory.create must return Runtime, got {type(candidate).__name__}"
        )
    return candidate


__all__ = ["RuntimeCapabilityClosure", "assemble_runtime_from_graph"]
