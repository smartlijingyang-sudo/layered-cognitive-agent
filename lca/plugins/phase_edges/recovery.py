"""Recovery phase edge plugin: reflect → think with failure detection.

This plugin provides a recovery edge from reflect to think phase when
the reflect phase detects a failure (observation.success == False).

The recovery is bounded: max 1 iteration to prevent infinite loops.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


class RecoveryEdgeConfig(BaseModel):
    """Configuration for recovery phase edge."""
    
    source: str = "reflect.main"
    target: str = "think.main"
    when: str = "result.admit_recovery"
    max_iterations: int = 1
    budget: str = "run.steps"


@plugin(
    id="phase.edge.reflect_to_think.recovery",
    Config=RecoveryEdgeConfig,
    provides=("phase.edge.recovery",),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects=EffectClass.NONE,
    test_suite="tests/declarative/test_recovery_edge.py",
)
async def setup(ctx: PluginContext, config: RecoveryEdgeConfig) -> None:
    """Provide recovery edge configuration.
    
    The edge is declarative and will be picked up by the compiler
    to add to the phase graph.
    """
    # Provide edge configuration as a capability
    ctx.provide(
        "phase.edge.recovery",
        {
            "source": config.source,
            "target": config.target,
            "when": config.when,
            "loop": {
                "max_iterations": config.max_iterations,
                "budget": config.budget,
                "terminal_predicate": "not result.admit_recovery",
            },
        },
    )
