"""spine_step_tree_accumulator — 试点 1 个 subscriber plugin（ADR-0181）。

迁移自 ``lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py``
的 spine.cognition.brain.perceive.start 处理部分；其余 deriver 留给 PR-8。
"""

from lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber import (
    SpineStepTreeAccumulator,
)

__all__ = ["SpineStepTreeAccumulator"]
