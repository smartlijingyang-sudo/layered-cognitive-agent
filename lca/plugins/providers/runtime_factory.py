"""Profile-selected factory for the default cognitive Agent Loop runtime.

The production assembly path depends only on ``RuntimeFactory``.  This plugin
owns the choice of ``CognitiveRuntime`` so a profile can replace the complete
loop implementation without modifying AgentGraph assembly or the gateway.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols.runtime_composition import RuntimeFactory
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.layer2_runtime.runtime_bindings import DeclarativeRuntimeBindings
from lca.layer2_runtime.runtime_loop import CognitiveRuntime


class Config(BaseModel):
    """Default cognitive runtime factory configuration."""

    model_config = {"extra": "forbid"}


class CognitiveRuntimeFactory(RuntimeFactory):
    """Create the standard six-step cognitive loop from verified bindings."""

    def create(self, bindings: object) -> CognitiveRuntime:
        """Fail closed unless the caller supplies immutable runtime bindings."""

        if not isinstance(bindings, DeclarativeRuntimeBindings):
            raise TypeError(
                "runtime_factory requires DeclarativeRuntimeBindings, "
                f"got {type(bindings).__name__}"
            )
        return CognitiveRuntime(bindings)


@plugin(
    id="lca-cognitive-runtime-factory",
    requires=[],
    provides=["runtime_factory"],
    implements=[RuntimeFactory],
    layer="L2",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide the default CognitiveRuntime factory so profiles can replace the entire "
        "Agent Loop without changing composition code."
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the profile-selected default Agent Loop implementation."""

    del config
    ctx.provide("runtime_factory", CognitiveRuntimeFactory())


__all__ = ["CognitiveRuntimeFactory", "Config", "setup"]
