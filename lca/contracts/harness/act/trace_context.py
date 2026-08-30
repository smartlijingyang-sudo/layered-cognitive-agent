"""Versioned trace context for reproducible Agent execution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentTraceContext:
    task_id: str
    step_id: str
    model_version: str
    tool_version: str
    policy_version: str

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.task_id,
                self.step_id,
                self.model_version,
                self.tool_version,
                self.policy_version,
            )
        ):
            raise ValueError("trace context identity and versions must not be empty")

    def as_attributes(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "step_id": self.step_id,
            "model_version": self.model_version,
            "tool_version": self.tool_version,
            "policy_version": self.policy_version,
        }


__all__ = ["AgentTraceContext"]
