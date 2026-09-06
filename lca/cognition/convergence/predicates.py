"""Pure delivery predicates — evidence fold only (ADR-0196)."""

from __future__ import annotations

from lca.contracts.models.core.policy.convergence import TaskClass


def delivery_satisfied(
    task_class: TaskClass,
    *,
    artifact_count: int,
    producer_ok: int,
    has_user_visible_delivery: bool,
) -> tuple[bool, str]:
    if task_class == "informative_text":
        if producer_ok >= 1 and (has_user_visible_delivery or artifact_count >= 1):
            return True, "informative_text: substantive output or artifact ready for respond"
        return False, "informative_text: awaiting substantive output or text respond"
    if task_class in {"visual_artifact", "code_demo", "mixed"}:
        if artifact_count >= 1 and producer_ok >= 1:
            return True, f"{task_class}: artifact present after producer success"
        return False, f"{task_class}: no harvestable artifact yet"
    if artifact_count >= 1 and producer_ok >= 1:
        return True, "unknown task class: artifact + producer success"
    if producer_ok >= 1 and has_user_visible_delivery:
        return True, "unknown: substantive producer output"
    return False, "unknown: insufficient delivery signals"


__all__ = ["delivery_satisfied"]
