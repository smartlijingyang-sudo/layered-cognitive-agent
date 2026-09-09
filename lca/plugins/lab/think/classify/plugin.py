"""think.classify — LLMResponse → Decision (lab action_type).

worker: classify(*, response, fixture_classifier) -> decision
kind: TRANSFORMER
out_port: decision
config: fixture_classifier
"""
from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.think.classify.ops import classify_response


def classify(
    *,
    response: Artifact | None,
    fixture_classifier: str | None = None,
) -> dict[str, Artifact]:
    """LLMResponse → Decision (lab action_type)。"""
    decision = classify_response(response, classifier=fixture_classifier)
    return {"decision": decision}


__all__ = ["classify"]
