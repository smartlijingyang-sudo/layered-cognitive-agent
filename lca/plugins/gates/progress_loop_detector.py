"""ProgressLoopDetector contribution — posts onto GateService."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.protocols import DecisionGate
from lca.plugins._cordis_adapter import plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    name="gate.progress-loop-detector",
    requires=["gates"],
    implements=[DecisionGate],
    layer="guard",
    side_effects="none",
    policy_class="control",
    description="Detect lack-of-progress loops and force a course change.",
    test_suite="tests/test_plugin_alignment.py",
)
async def setup(ctx, config: Config) -> None:
    from lca.layer1_cognitive.brain.decision_gates.progress_loop_detector import (
        ProgressLoopDetector,
    )

    ctx.inject("gates").add(
        ProgressLoopDetector, id="progress-loop-detector", slot="loop", order=30
    )
