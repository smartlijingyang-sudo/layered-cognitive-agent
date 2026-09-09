"""perceive.policy — Fold prior-step GateDecided policy facts.

worker: policy(*, state_artifact) -> policy_items
kind: TRANSFORMER
out_port: policy_items
in: state=state_artifact
"""
from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.perceive.ops import fold_policy_items


def policy(
    *,
    state_artifact: Artifact | None,
) -> dict[str, Artifact]:
    """Fold prior-step GateDecided policy facts from Session."""
    return fold_policy_items(state_artifact=state_artifact)


__all__ = ["policy"]
