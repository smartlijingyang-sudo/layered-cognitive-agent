"""Fixture-only runtime construction.

Production code never imports this module. Tests may supply a partial explicit
closure and use ``FixtureRuntimeAdapter`` to exercise the production runtime
binding without creating a second production assembly path.
"""

from __future__ import annotations

from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.plugins.composer.runtime.fixture_runtime_adapter import FixtureRuntimeAdapter
from lca.plugins.composer.runtime.fixture_runtime_input import RuntimeDeps
from lca.plugins.composer.runtime.runtime_binding import build_production_runtime_bindings
from lca.runtime.runtime_loop import CognitiveRuntime


class NullPerceiveHub:
    """Empty Perceive Hub for fixtures only."""

    async def perceive(self, _state: AgentState) -> ContextManifest:
        return ContextManifest(items=())


def build_fixture_cognitive_runtime(deps: RuntimeDeps) -> CognitiveRuntime:
    """Build the default runtime from explicit fixture dependencies."""

    production_deps = FixtureRuntimeAdapter(deps).to_production_runtime_deps()
    return CognitiveRuntime(build_production_runtime_bindings(production_deps))


__all__ = ["NullPerceiveHub", "RuntimeDeps", "build_fixture_cognitive_runtime"]
