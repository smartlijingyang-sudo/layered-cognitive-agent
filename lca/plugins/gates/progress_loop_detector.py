"""ProgressLoopDetector plugin — named factory ``gate.progress-loop-detector``."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import DecisionGate
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="gate.progress-loop-detector",
    provides=["gate.progress-loop-detector"],
    implements=[DecisionGate],
    layer="guard",
    side_effects="none",
    policy_class="control",
    description="Detect lack-of-progress loops and force a course change.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    """Provide the named gate factory ``gate.progress-loop-detector``."""
    from lca.layer1_cognitive.brain.decision_gates.progress_loop_detector import (
        ProgressLoopDetector,
    )

    ctx.provide("gate.progress-loop-detector", ProgressLoopDetector)
