"""perceive.trim — Concatenate Hub item streams + apply ContextBudgeter.trim.

worker: trim(*, sensor_items, memory_items, policy_items, max_chars) -> trimmed_items
kind: TRANSFORMER
out_port: trimmed_items
in: sensor_items=sensor_items memory_items=memory_items policy_items=policy_items
config: max_chars
"""
from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.perceive.ops import trim_items


def trim(
    *,
    sensor_items: Artifact | None,
    memory_items: Artifact | None,
    policy_items: Artifact | None,
    max_chars: int | None = None,
) -> dict[str, Artifact]:
    """Concatenate Hub item streams and apply ContextBudgeter.trim."""
    return trim_items(
        sensor_items=sensor_items,
        memory_items=memory_items,
        policy_items=policy_items,
        max_chars=max_chars,
    )


__all__ = ["trim"]
