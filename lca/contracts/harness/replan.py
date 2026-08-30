"""Safe dynamic re-planning requests for Hermes-style execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReplanAction(StrEnum):
    RETRY = "retry"
    REPLACE = "replace"
    ASK_USER = "ask_user"
    STOP = "stop"


@dataclass(frozen=True)
class ReplanRequest:
    """A bounded request to alter only the not-yet-executed task suffix."""

    task_id: str
    failed_step_id: str
    action: ReplanAction
    reason: str
    replacement: str | None = None
    affected_step_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.failed_step_id.strip():
            raise ValueError("task_id and failed_step_id must not be empty")
        if not self.reason.strip():
            raise ValueError("replan reason must not be empty")
        if self.action is ReplanAction.REPLACE and not self.replacement:
            raise ValueError("replace replan requires a replacement")
        if self.action is not ReplanAction.REPLACE and self.replacement is not None:
            raise ValueError("replacement is only valid for replace replan")
        if any(not step_id.strip() for step_id in self.affected_step_ids):
            raise ValueError("affected step IDs must not be empty")


def validate_replan_scope(
    request: ReplanRequest,
    *,
    completed_step_ids: frozenset[str] = frozenset(),
) -> None:
    """Fail closed when a replan attempts to mutate completed steps."""

    protected = completed_step_ids.intersection(request.affected_step_ids)
    if protected:
        joined = ", ".join(sorted(protected))
        raise ValueError(f"replan cannot mutate completed steps: {joined}")


__all__ = ["ReplanAction", "ReplanRequest", "validate_replan_scope"]
